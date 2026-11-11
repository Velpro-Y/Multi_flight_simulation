function run_ground_uturn_demo(requestFile, resultFile)
% Runtime-only controller wiring; the delivered SLX is never saved/overwritten.
request = jsondecode(fileread(requestFile));
if isfield(request,'differential_throttle'), differential=request.differential_throttle;
else, differential=0; end
assert(differential>=0 && differential<=0.1);
innerIdle=isfield(request,'thrust_policy') && strcmp(request.thrust_policy,'inner_idle');
accelOnly=isfield(request,'stage') && strcmp(request.stage,'accelerate');
outerCap=0.4; if isfield(request,'outer_throttle_cap'), outerCap=request.outer_throttle_cap; end
assert(outerCap>0 && outerCap<=0.4);
assignin('base','DemoCommand',[double(innerIdle);double(accelOnly);outerCap]);
largeTest=isfield(request,'large_angle_test') && request.large_angle_test;
maxAngle=10; rate=1;
if largeTest, maxAngle=75; rate=15; end
if largeTest && isfield(request,'steering_rate_deg_s')
    rate=request.steering_rate_deg_s; assert(rate>=1 && rate<=30);
end
assert(abs(request.nose_wheel_deg) > 0 && abs(request.nose_wheel_deg) <= maxAngle);
model = 'beaver_agent_env_ground_static_preserved';
load_system(fullfile(fileparts(mfilename('fullpath')), [model '.slx']));
cleanup = onCleanup(@() close_system(model, 0));
mw = get_param(model, 'ModelWorkspace');
g = getVariable(mw, 'GroundStatic');
g.InitialPosition = [0 0 -1.44]; g.InitialVelocity = [0 0 0];
g.InitialAttitude = [0 0 0]; g.InitialAngularRates = [0 0 0];
g.ParkingBrakeCmd = 0; g.PowerOff = 0;
assignin(mw, 'GroundStatic', g);
for name = {'AileronCmd','ElevatorCmd','RudderCmd','Throttle_Left','Throttle_Right'}
    assignin('base',name{1},0);
end
assignin('base','NoseWheelSteerCmdData',timeseries([0;0],[0;120]));

% Sample state for a small deterministic low-level controller at 20 Hz.
selector = find_system(model,'SearchDepth',1,'BlockType','BusSelector');
selector = selector{1};
ph = get_param(selector,'PortHandles');
add_block('simulink/Signal Routing/Mux',[model '/DemoStateMux'],'Inputs','4');
add_block('simulink/Discrete/Zero-Order Hold',[model '/DemoSample'],'SampleTime','0.05');
add_block('simulink/User-Defined Functions/MATLAB Function',[model '/DemoController']);
add_block('simulink/Sources/Constant',[model '/DemoCommand'],'Value','DemoCommand');
chart = find(sfroot,'-isa','Stateflow.EMChart','Path',[model '/DemoController']);
chart.Script = sprintf([ ...
    'function [throttle,steer,phase,done,right] = control(state,command)\n' ...
    'persistent mode angle integral\n' ...
    'if isempty(mode), mode=0; angle=0; integral=0; end\n' ...
    'speed=hypot(state(1),state(2)); yaw=state(3);\n' ...
    'target=5*0.5144444444; direction=%g; limit=%g*pi/180;\n' ...
    'if mode==0 && speed>=target, mode=1; end\n' ...
    'progress=direction*yaw*180/pi;\n' ...
    'reverse=state(1)*cos(yaw)-state(2)*sin(yaw)<0;\n' ...
    'if mode==1 && progress>=177 && reverse, mode=2; end\n' ...
    'if abs(state(4))>=10*pi/180, mode=3; end\n' ...
    'integral=min(5,max(-5,integral+(target-speed)*0.05));\n' ...
    'throttle=min(command(3),max(0,0.12+0.35*(target-speed)+0.08*integral));\n' ...
    'wanted=0; if mode==1, wanted=direction*min(limit,max(0,(180-progress)*0.5*pi/180)); end\n' ...
    'if %d && mode==1 && progress<150, wanted=direction*limit; end\n' ...
    'step=%g*pi/180*0.05; angle=angle+min(step,max(-step,wanted-angle));\n' ...
    'done=mode==2 || mode==3; if done, throttle=0; angle=0; end\n' ...
    'right=throttle; if mode==1\n' ...
    'if command(1)>0\n' ...
    'if direction>0, right=0; else, throttle=0; end\n' ...
    'else\n' ...
    'if direction>0, right=max(0,throttle-%g); else, throttle=max(0,throttle-%g); end\n' ...
    'end\n' ...
    'end\n' ...
    'steer=angle; phase=mode; done=done || (command(2)>0 && mode==1);\nend\n'],sign(request.nose_wheel_deg),abs(request.nose_wheel_deg),largeTest,rate,differential,differential);
mp = get_param([model '/DemoStateMux'],'PortHandles');
for k=1:4
    ports=[4 5 9 7]; add_line(model,ph.Outport(ports(k)),mp.Inport(k),'autorouting','on');
end
add_line(model,'DemoStateMux/1','DemoSample/1');
add_line(model,'DemoSample/1','DemoController/1');
add_line(model,'DemoCommand/1','DemoController/2');
cp = get_param([model '/DemoController'],'PortHandles');
replaceSource(model,'Throttle_Left',cp.Outport(1));
replaceSource(model,'Throttle_Right',cp.Outport(5));
replaceSource(model,'NoseWheelSteerCommand',cp.Outport(2));
add_block('simulink/Sinks/Stop Simulation',[model '/DemoStop']);
add_line(model,'DemoController/4','DemoStop/1');
for k=1:3
    names={'demoThrottle','demoSteering','demoPhase'};
    add_block('simulink/Sinks/To Workspace',[model '/' names{k}], ...
        'VariableName',names{k},'SaveFormat','Timeseries');
    add_line(model,sprintf('DemoController/%d',k),[names{k} '/1']);
end
add_block('simulink/Sinks/To Workspace',[model '/demoThrottleRight'], ...
    'VariableName','demoThrottleRight','SaveFormat','Timeseries');
add_line(model,'DemoController/5','demoThrottleRight/1');
wheelParent=[model '/GroundContactTireSteering/ThreePointGroundDynamics/NoseGear/WheelKinematics'];
wp=get_param([wheelParent '/WheelCos'],'PortHandles');
wheelSource=get_param(get_param(wp.Inport,'Line'),'SrcPortHandle');
add_block('simulink/Sinks/To Workspace',[wheelParent '/demoActualWheelAngle'], ...
    'VariableName','demoActualWheelAngle','SaveFormat','Timeseries');
wl=get_param([wheelParent '/demoActualWheelAngle'],'PortHandles');
add_line(wheelParent,wheelSource,wl.Inport);
for k=1:2
    propulsion={'Propulsion_Left','Propulsion_Right'};
    ph=get_param([model '/' propulsion{k}],'PortHandles');
    for j=1:2
        name=sprintf('demoPropulsion%d_%d',k,j);
        add_block('simulink/Sinks/To Workspace',[model '/' name], ...
            'VariableName',name,'SaveFormat','Timeseries');
        lp=get_param([model '/' name],'PortHandles');
        add_line(model,ph.Outport(j),lp.Inport,'autorouting','on');
    end
end
simArgs={'StopTime','120','ReturnWorkspaceOutputs','on','SaveOutput','off', ...
    'SaveFinalState','on','FinalStateName','xFinal','SaveCompleteFinalSimState','on'};
if isfield(request,'resume_file') && ~isempty(request.resume_file)
    checkpoint=load(request.resume_file,'xFinal','checkpointTime');
    assignin('base','DemoCheckpoint',checkpoint.xFinal);
    simArgs=[simArgs,{'LoadInitialState','on','InitialState','DemoCheckpoint', ...
        'StartTime',num2str(checkpoint.checkpointTime,17)}];
end
out=sim(model,simArgs{:});
if isfield(request,'checkpoint_file') && ~isempty(request.checkpoint_file)
    xFinal=out.xFinal; checkpointTime=out.tout(end);
    save(request.checkpoint_file,'xFinal','checkpointTime');
end
t=vec(out.tout); x=vec(out.Xe); y=vec(out.Ye);
h=rad2deg(unwrap(vec(out.psi))); roll=vec(out.phi);
u=vec(out.u); v=vec(out.v); contacts=vec(out.wheelContact);
change=h(end)-h(1); reverse=u(end)*cosd(h(end))-v(end)*sind(h(end))<0;
safe=all(isfinite([x;y;h;roll;u;v;contacts])) && ...
    max(abs(roll))<deg2rad(10) && all(contacts>0.5);
phase=vec(out.demoPhase); throttle=vec(out.demoThrottle); steering=vec(out.demoSteering);
result=struct('passed',safe && phase(end)==2 && reverse,'safe',safe, ...
    'start_time_s',t(1),'initial_x_m',x(1),'initial_y_m',y(1), ...
    'initial_heading_deg',h(1),'initial_speed_kn',hypot(u(1),v(1))/0.5144444444, ...
    'heading_change_deg',change,'reverse_motion',reverse,'duration_s',t(end), ...
    'final_x_m',x(end),'final_y_m',y(end),'max_abs_roll_deg',rad2deg(max(abs(roll))), ...
    'all_wheels_contact',all(contacts>0.5),'final_phase',phase(end), ...
    'differential_throttle',differential, ...
    'inner_idle',innerIdle, ...
    'requested_max_angle_deg',abs(request.nose_wheel_deg), ...
    'max_command_angle_deg',rad2deg(max(abs(steering))), ...
    'max_actual_front_wheel_angle_deg',rad2deg(max(abs(vec(out.demoActualWheelAngle)))), ...
    'steering_rate_limit_deg_s',rate, ...
    'forward_extent_m',max(x)-min(x),'lateral_extent_m',max(y)-min(y), ...
    'max_speed_kn',max(hypot(u,v))/0.5144444444, ...
    'final_speed_kn',hypot(u(end),v(end))/0.5144444444);
idx=unique(round(linspace(1,numel(t),min(501,numel(t)))));
result.trajectory=struct('time_s',t(idx),'x_m',x(idx),'y_m',y(idx), ...
    'heading_deg',h(idx),'speed_kn',hypot(u(idx),v(idx))/0.5144444444);
result.control=struct('time_s',out.demoPhase.Time,'phase',phase, ...
    'throttle_left',throttle,'throttle_right',vec(out.demoThrottleRight),'nose_wheel_deg',rad2deg(steering));
firstTurn=find(phase==1,1);
if ~isempty(firstTurn)
    start=out.demoPhase.Time(firstTurn);
    result.turn_start_s=start;
    turnMask=t>=start;
    result.min_turn_speed_kn=min(hypot(u(turnMask),v(turnMask)))/0.5144444444;
    moments=0;
    for k=1:2
        force=out.get(sprintf('demoPropulsion%d_1',k));
        f=squeeze(force.Data); if size(f,1)~=numel(force.Time), f=f'; end
        result.(sprintf('mean_turn_thrust%d_N',k))=mean(f(force.Time>=start,1));
        moment=out.get(sprintf('demoPropulsion%d_2',k));
        m=squeeze(moment.Data); if size(m,1)~=numel(moment.Time), m=m'; end
        moments=moments+mean(m(moment.Time>=start,3));
    end
    result.mean_turn_engine_yaw_moment_Nm=moments;
end
fid=fopen(resultFile,'w'); assert(fid>=0); fc=onCleanup(@() fclose(fid));
fprintf(fid,'%s',jsonencode(result));
end

function replaceSource(model,name,newSource)
path=[model '/' name]; p=get_param(path,'PortHandles');
line=get_param(p.Outport,'Line'); destinations=get_param(line,'DstPortHandle');
delete_line(line);
delete_block(path);
for k=1:numel(destinations), add_line(model,newSource,destinations(k),'autorouting','on'); end
end

function data=vec(signal)
if isa(signal,'timeseries'), data=signal.Data;
elseif isstruct(signal), data=signal.signals.values;
else, data=signal; end
data=data(:);
end
