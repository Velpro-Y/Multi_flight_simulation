function target = prepare_ground_brake_model
% Correct a copy of the supplied model. Never save the member's source file.
here=fileparts(mfilename('fullpath')); root=fileparts(here);
source=fullfile(root,'新增差动刹车和自动刹车','beaver_agent_env_ground_autobrake_steering.slx');
target=fullfile(here,'beaver_agent_env_ground_brake.slx');
original='beaver_agent_env_ground_autobrake_steering';
fixed='beaver_agent_env_ground_brake';
if bdIsLoaded(original), error('Close the supplied model before building its copy.'); end
if bdIsLoaded(fixed), error('Close the corrected model before rebuilding it.'); end
load_system(source); cleanup=onCleanup(@() closeIfLoaded(original)); %#ok<NASGU>
save_system(original,target); close_system(original,0);
load_system(target); cleanupFixed=onCleanup(@() closeIfLoaded(fixed)); %#ok<NASGU>
system=[fixed '/GroundContactTireSteering/BrakeSystemSelector'];
for side={'Left','Right'}
    block=[system '/Select' side{1} 'BrakeSystem'];
    assert(strcmp(get_param(block,'Criteria'),'u2 ~= 0'));
    p=get_param(block,'PortHandles');
    first=get_param(get_param(p.Inport(1),'Line'),'SrcPortHandle');
    third=get_param(get_param(p.Inport(3),'Line'),'SrcPortHandle');
    assert(contains(get_param(get_param(first,'Parent'),'Name'),['Differential' side{1}]));
    assert(strcmp(get_param(get_param(third,'Parent'),'Name'),'MinimumAutoBrakeDemand'));
    % A source can feed multiple branches: remove only the two destinations.
    delete_line(system,first,p.Inport(1)); delete_line(system,third,p.Inport(3));
    add_line(system,third,p.Inport(1),'autorouting','on');
    add_line(system,first,p.Inport(3),'autorouting','on');
end
set_param(fixed,'SimulationCommand','update');
save_system(fixed);
end

function closeIfLoaded(name)
if bdIsLoaded(name), close_system(name,0); end
end
