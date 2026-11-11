function run_ground_direction_demo(requestFile, resultFile)
% Fresh low-speed steering test; angles at the API boundary are degrees.
request = jsondecode(fileread(requestFile));
assert(abs(request.nose_wheel_deg) <= 10);
assert(request.initial_speed_kn > 0 && request.initial_speed_kn <= 5);
assert(request.duration_s >= 1 && request.duration_s <= 8);
model = 'beaver_agent_env_ground_static_preserved';
load_system(fullfile(fileparts(mfilename('fullpath')), [model '.slx']));
cleanup = onCleanup(@() close_system(model, 0));
workspace = get_param(model, 'ModelWorkspace');
ground = getVariable(workspace, 'GroundStatic');
ground.InitialPosition = [0 0 -1.44];
ground.InitialVelocity = [request.initial_speed_kn * 0.5144444444 0 0];
ground.InitialAttitude = [0 0 0];
ground.InitialAngularRates = [0 0 0];
ground.ParkingBrakeCmd = 0;
ground.PowerOff = 1;
assignin(workspace, 'GroundStatic', ground);
names = {'RudderCmd','AileronCmd','ElevatorCmd','Throttle_Left','Throttle_Right'};
for i = 1:numel(names)
    assignin('base', names{i}, 0);
end
angle = deg2rad(request.nose_wheel_deg);
assignin('base', 'NoseWheelSteerCmdData', ...
    timeseries([angle;angle], [0;request.duration_s]));
out = sim(model, 'StopTime', num2str(request.duration_s), ...
    'ReturnWorkspaceOutputs', 'on', 'SaveOutput', 'off');
t = values(out.tout); t = t(:);
x = values(out.Xe); x = x(:);
y = values(out.Ye); y = y(:);
heading = unwrap(values(out.psi)); heading = heading(:);
roll = values(out.phi);
contacts = values(out.wheelContact);
u = values(out.u); v = values(out.v);
change = rad2deg(heading(end) - heading(1));
finite = all(isfinite([x(:);y(:);heading(:);roll(:);u(:);v(:);contacts(:)]));
safe = finite && max(abs(roll(:))) < deg2rad(10) && all(contacts(:) > 0.5);
if abs(request.nose_wheel_deg) < 1e-6
    response = abs(change) < 2 && abs(y(end)-y(1)) < 0.5;
else
    response = sign(request.nose_wheel_deg)*change > 1 && ...
        sign(request.nose_wheel_deg)*(y(end)-y(1)) > 0.1;
end
result = struct('passed', safe && response, 'safe', safe, ...
    'direction_response', response, 'heading_change_deg', change, ...
    'final_x_m', x(end), 'final_y_m', y(end), ...
    'max_abs_roll_deg', rad2deg(max(abs(roll(:)))), ...
    'all_wheels_contact', all(contacts(:) > 0.5), ...
    'final_body_horizontal_speed_m_s', hypot(u(end),v(end)));
% Downsample only the returned trajectory; validation uses every sample.
idx = unique(round(linspace(1, numel(t), min(101, numel(t)))));
result.trajectory = struct('time_s',t(idx), 'x_m',x(idx), 'y_m',y(idx), ...
    'heading_deg',rad2deg(heading(idx)));
fid = fopen(resultFile, 'w');
assert(fid >= 0, 'Cannot open result file');
fileCleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonencode(result));
end

function data = values(signal)
if isa(signal, 'timeseries')
    data = squeeze(signal.Data);
elseif isstruct(signal) && isfield(signal, 'signals')
    data = squeeze(signal.signals.values);
else
    data = signal;
end
end
