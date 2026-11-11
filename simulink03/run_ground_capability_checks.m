function run_ground_capability_checks(outputDir)
% Four targeted checks in one MATLAB process; no SLX is saved.
if ~exist(outputDir,'dir'), mkdir(outputDir); end
model='beaver_agent_env_ground_static_preserved';
cases={'static_75','symmetric','reduce_left','reduce_right'};
summaries=cell(1,4);
for c=1:4
    load_system(fullfile(fileparts(mfilename('fullpath')),[model '.slx']));
    cleanup=onCleanup(@() close_system(model,0));
    mw=get_param(model,'ModelWorkspace'); g=getVariable(mw,'GroundStatic');
    g.InitialPosition=[0 0 -1.44]; g.InitialVelocity=[0 0 0];
    g.InitialAttitude=[0 0 0]; g.InitialAngularRates=[0 0 0];
    g.ParkingBrakeCmd=double(c==1); g.PowerOff=double(c==1);
    assignin(mw,'GroundStatic',g);
    for n={'AileronCmd','ElevatorCmd','RudderCmd','Throttle_Left','Throttle_Right'}
        assignin('base',n{1},0);
    end
    times=[0;5;7;17;19;24]; angles=deg2rad([0;75;75;-75;-75;0]);
    if c~=1, angles(:)=0; end
    assignin('base','NoseWheelSteerCmdData',timeseries(angles,times));
    gears={'NoseGear','LeftMainGear','RightMainGear'};
    for k=1:3
        parent=[model '/GroundContactTireSteering/ThreePointGroundDynamics/' gears{k} '/WheelKinematics'];
        ph=get_param([parent '/WheelCos'],'PortHandles');
        source=get_param(get_param(ph.Inport,'Line'),'SrcPortHandle');
        logSignal(parent,source,sprintf('checkWheel%d',k));
    end
    for k=1:2
        names={'Propulsion_Left','Propulsion_Right'};
        ph=get_param([model '/' names{k}],'PortHandles');
        logSignal(model,ph.Outport(1),sprintf('checkForce%d',k));
    end
    if c>1
        addController(model,c);
    end
    out=sim(model,'StopTime',num2str(24+36*(c>1)), ...
        'ReturnWorkspaceOutputs','on','SaveOutput','off');
    t=vec(out.tout); h=rad2deg(unwrap(vec(out.psi))); x=vec(out.Xe); y=vec(out.Ye);
    u=vec(out.u); v=vec(out.v); roll=vec(out.phi); contact=vec(out.wheelContact);
    safe=all(isfinite([t;h;x;y;u;v;roll;contact])) && ...
        max(abs(roll))<deg2rad(10) && all(contact>0.5);
    s=struct('case_id',cases{c},'safe',safe,'duration_s',t(end), ...
        'heading_change_deg',h(end)-h(1),'final_y_m',y(end), ...
        'max_abs_roll_deg',rad2deg(max(abs(roll))),'all_wheels_contact',all(contact>0.5));
    for k=1:3
        wheel=rad2deg(vec(out.get(sprintf('checkWheel%d',k))));
        s.(sprintf('wheel%d_min_deg',k))=min(wheel);
        s.(sprintf('wheel%d_max_deg',k))=max(wheel);
    end
    s.max_speed_kn=max(hypot(u,v))/0.5144444444;
    if c==1
        s.passed=safe && abs(s.wheel1_max_deg-75)<0.01 && ...
            abs(s.wheel1_min_deg+75)<0.01 && ...
            max(abs([s.wheel2_min_deg,s.wheel2_max_deg,s.wheel3_min_deg,s.wheel3_max_deg]))<0.01 && ...
            s.max_speed_kn<0.01;
    else
        controls=out.checkControl; state=squeeze(controls.Data);
        if size(state,1)~=numel(controls.Time), state=state'; end
        ix=find(state(:,3)>=1,1); s.accelerated_to_5kn=~isempty(ix);
        if isempty(ix), start=inf; else, start=controls.Time(ix); end
        s.differential_start_s=start;
        tt=controls.Time; mask=tt>=start;
        s.final_left_throttle=state(end,1); s.final_right_throttle=state(end,2);
        headings=interp1(t,h,tt,'linear');
        if any(mask), s.post_heading_change_deg=headings(end)-headings(ix);
        else, s.post_heading_change_deg=0; end
        for k=1:2
            force=out.get(sprintf('checkForce%d',k));
            values=squeeze(force.Data); if size(values,1)~=numel(force.Time), values=values'; end
            active=force.Time>=start;
            s.(sprintf('mean_thrust%d_N',k))=mean(values(active,1));
        end
        s.passed=safe && s.accelerated_to_5kn && ...
            abs(s.wheel1_max_deg)<0.01 && abs(s.wheel1_min_deg)<0.01;
    end
    idx=unique(round(linspace(1,numel(t),min(301,numel(t)))));
    trajectory=struct('time_s',t(idx),'x_m',x(idx),'y_m',y(idx), ...
        'heading_deg',h(idx),'speed_kn',hypot(u(idx),v(idx))/0.5144444444);
    save(fullfile(outputDir,[cases{c} '.mat']),'out');
    writeJson(fullfile(outputDir,[cases{c} '.json']),struct('summary',s,'trajectory',trajectory));
    summaries{c}=s;
    clear cleanup;
end
% Recompute comparisons from raw logs with explicit signal-shape handling.
finalize_ground_capability_checks(outputDir);
end

function addController(model,caseIndex)
selector=find_system(model,'SearchDepth',1,'BlockType','BusSelector');
ph=get_param(selector{1},'PortHandles');
add_block('simulink/Signal Routing/Mux',[model '/CheckState'],'Inputs','2');
mp=get_param([model '/CheckState'],'PortHandles');
add_line(model,ph.Outport(4),mp.Inport(1)); add_line(model,ph.Outport(5),mp.Inport(2));
add_block('simulink/Discrete/Zero-Order Hold',[model '/CheckSample'],'SampleTime','0.05');
add_block('simulink/User-Defined Functions/MATLAB Function',[model '/CheckController']);
chart=find(sfroot,'-isa','Stateflow.EMChart','Path',[model '/CheckController']);
chart.Script=sprintf([ ...
    'function [left,right,done,record]=control(state)\n' ...
    'persistent mode integral elapsed\n' ...
    'if isempty(mode), mode=0; integral=0; elapsed=0; end\n' ...
    'speed=hypot(state(1),state(2)); target=5*0.5144444444;\n' ...
    'if mode==0 && speed>=target, mode=1; end\n' ...
    'integral=min(5,max(-5,integral+(target-speed)*0.05));\n' ...
    'common=min(0.4,max(0,0.12+0.35*(target-speed)+0.08*integral));\n' ...
    'left=common; right=common;\n' ...
    'if mode==1\n' ...
    'elapsed=elapsed+0.05; left=0.22; right=0.22;\n' ...
    'if %d==3, left=0.12; end\n' ...
    'if %d==4, right=0.12; end\n' ...
    'end\n' ...
    'done=elapsed>=8; record=[left,right,mode];\nend\n'],caseIndex,caseIndex);
add_line(model,'CheckState/1','CheckSample/1');
add_line(model,'CheckSample/1','CheckController/1');
cp=get_param([model '/CheckController'],'PortHandles');
replaceSource(model,'Throttle_Left',cp.Outport(1));
replaceSource(model,'Throttle_Right',cp.Outport(2));
add_block('simulink/Sinks/Stop Simulation',[model '/CheckStop']);
add_line(model,'CheckController/3','CheckStop/1');
logSignal(model,cp.Outport(4),'checkControl');
end

function replaceSource(model,name,source)
ph=get_param([model '/' name],'PortHandles');
line=get_param(ph.Outport,'Line'); dst=get_param(line,'DstPortHandle');
delete_line(line); delete_block([model '/' name]);
for k=1:numel(dst), add_line(model,source,dst(k),'autorouting','on'); end
end

function logSignal(parent,source,name)
add_block('simulink/Sinks/To Workspace',[parent '/' name], ...
    'VariableName',name,'SaveFormat','Timeseries');
p=get_param([parent '/' name],'PortHandles');
add_line(parent,source,p.Inport,'autorouting','on');
end

function data=vec(signal)
if isa(signal,'timeseries'), data=signal.Data;
elseif isstruct(signal), data=signal.signals.values;
else, data=signal; end
data=data(:);
end

function writeJson(path,value)
fid=fopen(path,'w'); assert(fid>=0); cleanup=onCleanup(@() fclose(fid));
fprintf(fid,'%s',jsonencode(value));
end
