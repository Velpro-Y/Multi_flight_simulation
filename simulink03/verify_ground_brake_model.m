function verify_ground_brake_model(outputDir)
% Bounded physical tests; no Dify calls, no changes to source-model defaults.
if ~exist(outputDir,'dir'), mkdir(outputDir); end
fixedFile=prepare_ground_brake_model;
model='beaver_agent_env_ground_brake'; load_system(fixedFile);
cleanup=onCleanup(@() close_system(model,0)); %#ok<NASGU>
mw=get_param(model,'ModelWorkspace'); original=getVariable(mw,'GroundStatic');
writeJson(fullfile(outputDir,'ground_static_defaults.json'),original);
base=original;
base.PowerOff=1; base.ParkingBrakeCmd=0; base.GearDown=1;
base.InitialPositionOffset=[0 0 0]; base.InitialVelocity=[2.57 0 0];
base.InitialAttitude=[0 0 0]; base.InitialAngularRates=[0 0 0];
base.BrakeSystemMode=0; base.BrakeMode=0;
base.LeftBrakeManual=0; base.RightBrakeManual=0;
base.AutoBrakePreArm=0; base.AutoBrakeMinLevel=0.15;
base.NoseSteerLowSpeed=2; base.NoseSteerHighSpeed=20;
base.NoseSteerAngleLowSpeed=deg2rad(75); base.NoseSteerAngleHighSpeed=deg2rad(6);
results=struct([]);

g=base; g.LeftBrakeManual=0.2;
a=runCase('manual_left',g,0,0.1); results=append(results,a);
g=base; g.RightBrakeManual=0.2;
b=runCase('manual_right',g,0,0.1); results=append(results,b);
g=base;
c=runCase('coast',g,0,0.5); results=append(results,c);
g=base; g.BrakeSystemMode=1; g.AutoBrakePreArm=1;
g.LeftBrakeManual=0.7; g.RightBrakeManual=0.2;
d=runCase('auto_ground',g,0,0.5); results=append(results,d);
g.AutoBrakePreArm=0;
e=runCase('auto_disarmed',g,0,0.2); results=append(results,e);
g=base; g.BrakeSystemMode=1; g.AutoBrakePreArm=1;
g.InitialPositionOffset=[0 0 -0.15];
f=runCase('auto_touchdown',g,0,1.0); results=append(results,f);
for item={struct('name','steer_low','speed',1), ...
          struct('name','steer_5kn','speed',5*0.5144444444), ...
          struct('name','steer_high','speed',25)}
    g=base; g.InitialVelocity=[item{1}.speed 0 0];
    value=runCase(item{1}.name,g,75,0.02); results=append(results,value);
end
g=base;
r=runCase('turn_right_10',g,10,8); results=append(results,r);
l=runCase('turn_left_10',g,-10,8); results=append(results,l);

checks=struct;
checks.left_brake_routing=abs(a.initial_left_brake-0.2)<1e-8 && abs(a.initial_right_brake)<1e-8;
checks.right_brake_routing=abs(b.initial_right_brake-0.2)<1e-8 && abs(b.initial_left_brake)<1e-8;
checks.opposite_yaw_moments=a.initial_yaw_moment_Nm<0 && b.initial_yaw_moment_Nm>0;
checks.auto_symmetric_and_exclusive=d.final_auto_active>0.5 && ...
    abs(d.final_left_brake-0.15)<1e-8 && abs(d.final_right_brake-0.15)<1e-8;
checks.auto_decelerates_more_than_coast=d.final_speed_m_s<c.final_speed_m_s;
checks.disarmed_no_auto=e.max_auto_active<0.5 && abs(e.final_left_brake)<1e-8 && abs(e.final_right_brake)<1e-8;
checks.touchdown_trigger=f.initial_auto_active<0.5 && isfinite(f.first_contact_s) && ...
    isfinite(f.first_auto_s) && f.first_auto_s>=f.first_contact_s-1e-8 && f.first_auto_s>0;
for n=7:9
    speed=results(n).initial_speed_m_s;
    limit=75+(6-75)*min(1,max(0,(speed-2)/18));
    checks.(['schedule_' results(n).case_id])=abs(results(n).initial_steering_limit_deg-limit)<1e-6 && ...
        abs(results(n).initial_steering_command_deg-limit)<1e-6;
end
checks.turn_direction_and_contact=r.heading_change_deg>1 && l.heading_change_deg<-1 && ...
    r.all_wheels_contact && l.all_wheels_contact && r.max_abs_roll_deg<10 && l.max_abs_roll_deg<10;
checks.finite=all([results.finite]);
summary=struct('model',fixedFile,'passed',all(structfun(@(v) logical(v),checks)), ...
    'checks',checks,'cases',results,'scope','Physical model smoke tests; no Dify calls');
writeJson(fullfile(outputDir,'summary.json'),summary);
fprintf('BRAKE_VERIFICATION %s\n',jsonencode(summary));

    function metric=runCase(name,g,angle,stop)
        assignin(mw,'GroundStatic',g);
        for key={'AileronCmd','ElevatorCmd','RudderCmd','Throttle_Left','Throttle_Right'}
            assignin('base',key{1},0);
        end
        assignin('base','NoseWheelSteerCmdData',timeseries(deg2rad([angle;angle]),[0;stop]));
        in=Simulink.SimulationInput(model);
        in=in.setModelParameter('StartTime','0','StopTime',num2str(stop,17), ...
            'LoadInitialState','off','SaveOutput','off');
        out=sim(in);
        t=vec(out.tout); u=vec(out.u); v=vec(out.v); roll=vec(out.phi); psi=vec(out.psi);
        left=out.get('leftMainBrakeCommand'); right=out.get('rightMainBrakeCommand');
        active=out.get('autoBrakeActive'); contact=out.get('wheelContact');
        lim=out.get('noseSteeringLimitRad'); cmd=out.get('noseSteeringCommandRad');
        moment=out.get('groundMoments');
        cd=squeeze(contact.Data); if size(cd,1)~=numel(contact.Time), cd=cd'; end
        if size(cd,2)~=3 && numel(cd)==numel(contact.Time)*3, cd=reshape(cd,[],3); end
        contactIndex=find(any(cd>0.5,2),1); autoIndex=find(vec(active)>0.5,1);
        firstContact=NaN; firstAuto=NaN;
        if ~isempty(contactIndex), firstContact=contact.Time(contactIndex); end
        if ~isempty(autoIndex), firstAuto=active.Time(autoIndex); end
        md=squeeze(moment.Data); if size(md,1)~=numel(moment.Time), md=md'; end
        metric=struct('case_id',name,'initial_speed_m_s',hypot(u(1),v(1)), ...
            'final_speed_m_s',hypot(u(end),v(end)),'duration_s',t(end), ...
            'initial_left_brake',left.Data(1),'initial_right_brake',right.Data(1), ...
            'final_left_brake',left.Data(end),'final_right_brake',right.Data(end), ...
            'initial_auto_active',active.Data(1),'final_auto_active',active.Data(end), ...
            'max_auto_active',max(vec(active)),'first_contact_s',firstContact,'first_auto_s',firstAuto, ...
            'initial_yaw_moment_Nm',md(1,3),'heading_change_deg',rad2deg(psi(end)-psi(1)), ...
            'initial_steering_limit_deg',rad2deg(lim.Data(1)), ...
            'initial_steering_command_deg',rad2deg(cmd.Data(1)), ...
            'all_wheels_contact',all(cd(:)>0.5),'max_abs_roll_deg',rad2deg(max(abs(roll))), ...
            'finite',all(isfinite([t;u;v;roll;psi;vec(left);vec(right);vec(lim);vec(cmd)])));
        idx=unique(round(linspace(1,numel(t),min(501,numel(t)))));
        trace=struct('time_s',t(idx),'speed_m_s',hypot(u(idx),v(idx)), ...
            'heading_deg',rad2deg(psi(idx)),'roll_deg',rad2deg(roll(idx)));
        writeJson(fullfile(outputDir,[name '.json']),struct('configuration',g,'requested_nose_deg',angle,'metric',metric,'trajectory',trace));
        fprintf('CASE %s %s\n',name,jsonencode(metric));
    end
end

function a=append(a,b)
if isempty(a), a=b; else, a(end+1)=b; end
end
function x=vec(signal)
if isa(signal,'timeseries'), x=signal.Data; else, x=signal; end
x=x(:);
end
function writeJson(path,obj)
fid=fopen(path,'w'); assert(fid>=0); c=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(obj));
end
