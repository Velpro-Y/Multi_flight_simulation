function probe_brake_correction(outputDir)
% Check the specified 100kn condition before spending Dify calls.
if ~exist(outputDir,'dir'), mkdir(outputDir); end
here=fileparts(mfilename('fullpath')); model='beaver_agent_env_ground_brake';
previousFolder=pwd; restoreFolder=onCleanup(@() cd(previousFolder)); %#ok<NASGU>
cd(outputDir);
load_system(fullfile(here,[model '.slx']));
cleanup=onCleanup(@() close_system(model,0)); %#ok<NASGU>
mw=get_param(model,'ModelWorkspace'); original=getVariable(mw,'GroundStatic');
for key={'AileronCmd','ElevatorCmd','RudderCmd','Throttle_Left','Throttle_Right'}
    assignin('base',key{1},0);
end
assignin('base','NoseWheelSteerCmdData',timeseries([0;0],[0;0.25]));
results=struct([]);
for side=0:2
    g=original; g.PowerOff=1; g.ParkingBrakeCmd=0;
    g.InitialPosition=[0 60*.3048 -1.44];
    g.InitialPositionOffset=[0 0 0];
    g.InitialVelocity=[100*.5144444444 0 0];
    g.InitialAttitude=[0 0 deg2rad(2)]; g.InitialAngularRates=[0 0 0];
    g.BrakeSystemMode=0; g.BrakeMode=0; g.AutoBrakePreArm=0;
    g.LeftBrakeManual=.1*(side==1); g.RightBrakeManual=.1*(side==2);
    assignin(mw,'GroundStatic',g);
    in=Simulink.SimulationInput(model);
    in=in.setModelParameter('StartTime','0','StopTime','0.25','LoadInitialState','off','SaveOutput','off');
    out=sim(in);
    t=vec(out.tout);u=vec(out.u);v=vec(out.v);x=vec(out.Xe);y=vec(out.Ye);
    phi=vec(out.phi);psi=vec(out.psi);r=vec(out.r);contact=vec(out.wheelContact);
    moment=out.get('groundMoments'); md=squeeze(moment.Data);
    if size(md,1)~=numel(moment.Time), md=md'; end
    metric=struct('case_id',side,'requested_speed_kn',100,'initial_speed_kn',hypot(u(1),v(1))/.5144444444, ...
        'initial_y_m',y(1),'initial_heading_deg',rad2deg(psi(1)), ...
        'final_y_m',y(end),'final_heading_deg',rad2deg(psi(end)), ...
        'final_yaw_rate_deg_s',rad2deg(r(end)),'initial_yaw_moment_Nm',md(1,3), ...
        'all_wheels_contact',all(contact>.5),'max_abs_roll_deg',rad2deg(max(abs(phi))), ...
        'finite',all(isfinite([t;u;v;x;y;phi;psi;r;contact])));
    if isempty(results), results=metric; else, results(end+1)=metric; end %#ok<AGROW>
    fprintf('PROBE %s\n',jsonencode(metric));
end
fid=fopen(fullfile(outputDir,'summary.json'),'w'); assert(fid>=0);
fprintf(fid,'%s',jsonencode(struct('model',model,'cases',results,'dify_calls',0))); fclose(fid);
end

function x=vec(signal)
if isa(signal,'timeseries'), x=signal.Data; else, x=signal; end
x=x(:);
end
