function ground_realtime_worker(folder)
% One MATLAB process, continuous operating-point state, direct LLM controls.
model='beaver_agent_env_ground_static_preserved';
load_system(fullfile(fileparts(mfilename('fullpath')),[model '.slx']));
cleanup=onCleanup(@() close_system(model,0));
mw=get_param(model,'ModelWorkspace'); g=getVariable(mw,'GroundStatic');
g.InitialPosition=[0 0 -1.44]; g.InitialVelocity=[0 0 0];
g.InitialAttitude=[0 0 0]; g.InitialAngularRates=[0 0 0];
g.PowerOff=0; g.ParkingBrakeCmd=0; assignin(mw,'GroundStatic',g);
for n={'AileronCmd','ElevatorCmd','RudderCmd','Throttle_Left','Throttle_Right','RtLeft','RtRight','RtNose'}
    assignin('base',n{1},0);
end
set_param([model '/Throttle_Left'],'Value','RtLeft');
set_param([model '/Throttle_Right'],'Value','RtRight');
p=get_param([model '/NoseWheelSteerCommand'],'PortHandles');
line=get_param(p.Outport,'Line'); dst=get_param(line,'DstPortHandle');
delete_line(line); delete_block([model '/NoseWheelSteerCommand']);
add_block('simulink/Sources/Constant',[model '/RtWheelCommand'],'Value','RtNose');
% Discrete actuator rate protection avoids a continuous Rate Limiter solver
% stall when an operating point is resumed with a new steering command.
add_block('simulink/Sources/Clock',[model '/RtClock']);
add_block('simulink/Discrete/Zero-Order Hold',[model '/RtClockSample'],'SampleTime','0.01');
add_block('simulink/Signal Routing/Mux',[model '/RtRateInput'],'Inputs','2');
add_block('simulink/User-Defined Functions/MATLAB Function',[model '/RtWheelRate']);
chart=find(sfroot,'-isa','Stateflow.EMChart','Path',[model '/RtWheelRate']);
chart.Script=sprintf(['function angle=rate(u)\npersistent value lastTime\n' ...
    'if isempty(value), value=0; lastTime=-1; end\n' ...
    'if u(2)>lastTime+1e-9\n' ...
    'limit=30*pi/180*0.01; value=value+min(limit,max(-limit,u(1)-value)); lastTime=u(2);\n' ...
    'end\nangle=value;\nend\n']);
add_line(model,'RtClock/1','RtClockSample/1');
add_line(model,'RtClockSample/1','RtRateInput/2');
add_line(model,'RtWheelCommand/1','RtRateInput/1');
add_line(model,'RtRateInput/1','RtWheelRate/1');
rp=get_param([model '/RtWheelRate'],'PortHandles');
for k=1:numel(dst), add_line(model,rp.Outport,dst(k),'autorouting','on'); end
wp=[model '/GroundContactTireSteering/ThreePointGroundDynamics/NoseGear/WheelKinematics'];
ph=get_param([wp '/WheelCos'],'PortHandles'); src=get_param(get_param(ph.Inport,'Line'),'SrcPortHandle');
add_block('simulink/Sinks/To Workspace',[wp '/rtActualWheel'], ...
    'VariableName','rtActualWheel','SaveFormat','Timeseries');
lp=get_param([wp '/rtActualWheel'],'PortHandles'); add_line(wp,src,lp.Inport);
% Stop on heading completion or excessive roll, even within a 0.5s command.
selector=find_system(model,'SearchDepth',1,'BlockType','BusSelector');
sp=get_param(selector{1},'PortHandles');
add_block('simulink/Signal Routing/Mux',[model '/RtWatch'],'Inputs','2');
mp=get_param([model '/RtWatch'],'PortHandles');
add_line(model,sp.Outport(9),mp.Inport(1)); add_line(model,sp.Outport(7),mp.Inport(2));
add_block('simulink/Discrete/Zero-Order Hold',[model '/RtWatchSample'],'SampleTime','0.01');
add_block('simulink/User-Defined Functions/Fcn',[model '/RtStopCondition'], ...
    'Expr','(u(1)>=177*pi/180)||(abs(u(2))>=10*pi/180)');
add_block('simulink/Sinks/Stop Simulation',[model '/RtStop']);
add_line(model,'RtWatch/1','RtWatchSample/1'); add_line(model,'RtWatchSample/1','RtStopCondition/1');
add_line(model,'RtStopCondition/1','RtStop/1');
set_param(model,'SaveOutput','off','SaveFinalState','on','FinalStateName','xFinal', ...
    'SaveCompleteFinalSimState','on');
set_param(model,'FastRestart','on');
writeJson(fullfile(folder,'ready.json'),struct('ready',true));
time=0; checkpoint=[];
for seq=1:40
    requestFile=fullfile(folder,sprintf('request_%03d.json',seq));
    timer=tic;
    while ~exist(requestFile,'file')
        if exist(fullfile(folder,'stop.flag'),'file') || toc(timer)>180, return; end
        pause(0.1);
    end
    try
        request=jsondecode(fileread(requestFile));
        assert(request.throttle_left>=0 && request.throttle_left<=0.4);
        assert(request.throttle_right>=0 && request.throttle_right<=0.4);
        assert(abs(request.nose_wheel_deg)<=75);
        in=Simulink.SimulationInput(model);
        in=in.setVariable('RtLeft',request.throttle_left);
        in=in.setVariable('RtRight',request.throttle_right);
        in=in.setVariable('RtNose',deg2rad(request.nose_wheel_deg));
        in=in.setModelParameter('StopTime',num2str(time+0.5,17));
        if ~isempty(checkpoint), in=in.setInitialState(checkpoint); end
        out=sim(in); checkpoint=out.xFinal;
        t=vec(out.tout); x=vec(out.Xe); y=vec(out.Ye); psi=vec(out.psi);
        roll=vec(out.phi); u=vec(out.u); v=vec(out.v); r=vec(out.r);
        contact=vec(out.wheelContact); wheel=rad2deg(vec(out.rtActualWheel));
        time=t(end);
        safe=all(isfinite([t;x;y;psi;roll;u;v;r;contact;wheel])) && ...
            max(abs(roll))<deg2rad(10) && all(contact>0.5);
        reverse=u(end)*cos(psi(end))-v(end)*sin(psi(end))<0;
        complete=safe && rad2deg(psi(end))>=177 && reverse;
        idx=unique(round(linspace(1,numel(t),min(31,numel(t)))));
        result=struct('safe',safe,'complete',complete,'on_ground',all(contact>0.5), ...
            'time_s',time,'start_time_s',t(1),'initial_x_m',x(1),'initial_y_m',y(1), ...
            'initial_speed_kn',hypot(u(1),v(1))/0.5144444444, ...
            'x_m',x(end),'y_m',y(end),'speed_kn',hypot(u(end),v(end))/0.5144444444, ...
            'heading_deg',rad2deg(psi(end)),'yaw_rate_deg_s',rad2deg(r(end)), ...
            'roll_deg',rad2deg(roll(end)),'max_abs_roll_deg',rad2deg(max(abs(roll))), ...
            'wheel_deg',wheel(end),'max_wheel_deg',max(abs(wheel)), ...
            'max_speed_kn',max(hypot(u,v))/0.5144444444, ...
            'trajectory',struct('time_s',t(idx),'x_m',x(idx),'y_m',y(idx), ...
            'heading_deg',rad2deg(psi(idx)),'speed_kn',hypot(u(idx),v(idx))/0.5144444444));
        writeJson(fullfile(folder,sprintf('response_%03d.json',seq)),result);
        if complete || ~safe, break; end
    catch exception
        writeJson(fullfile(folder,sprintf('response_%03d.json',seq)),struct('error',getReport(exception,'extended','hyperlinks','off')));
        break;
    end
end
set_param(model,'FastRestart','off');
end

function value=vec(signal)
if isa(signal,'timeseries'), value=signal.Data;
elseif isstruct(signal), value=signal.signals.values;
else, value=signal; end
value=value(:);
end

function writeJson(path,value)
temporary=[path '.tmp']; fid=fopen(temporary,'w'); assert(fid>=0);
fprintf(fid,'%s',jsonencode(value)); fclose(fid); movefile(temporary,path,'f');
end
