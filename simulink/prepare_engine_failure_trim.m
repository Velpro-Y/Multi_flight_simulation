function result = prepare_engine_failure_trim(initialAltitudeFt, airspeedFtS, failureAltitudeFt, goAroundAltitudeFt)
%PREPARE_ENGINE_FAILURE_TRIM Compute scene-one trims without changing the source model.

arguments
    initialAltitudeFt (1,1) double {mustBeFinite,mustBePositive}
    airspeedFtS (1,1) double {mustBeFinite,mustBePositive}
    failureAltitudeFt (1,1) double {mustBeFinite,mustBePositive}
    goAroundAltitudeFt (1,1) double {mustBeFinite,mustBePositive}
end

thisDir = fileparts(mfilename('fullpath'));
oldDir = pwd;
cleanupDir = onCleanup(@() cd(oldDir)); %#ok<NASGU>
cd(thisDir);

sourceModel = 'beaver_agent_env';
temporaryBase = tempname;
[temporaryDir, runtimeModel] = fileparts(temporaryBase);
runtimeFile = fullfile(temporaryDir, [runtimeModel '.slx']);

if bdIsLoaded(sourceModel), close_system(sourceModel, 0); end
load_system(sourceModel);
save_system(sourceModel, runtimeFile);
close_system(sourceModel, 0);
cleanupSource = onCleanup(@() ensure_source_loaded(sourceModel)); %#ok<NASGU>
load_system(runtimeModel);
cleanupModel = onCleanup(@() cleanup_runtime_model(runtimeModel, runtimeFile)); %#ok<NASGU>

make_trim_inputs(runtimeModel);
evalin('base', '[aircraft, state] = astDehavillandBeaver();');

metersPerFoot = 0.3048;
metersPerSecondPerFootPerSecond = 0.3048;
targetU = airspeedFtS * metersPerSecondPerFootPerSecond;

cases = struct( ...
    'name', {'twin_descent','engine_out_descent','engine_out_climb'}, ...
    'altitude_m', {initialAltitudeFt * metersPerFoot, ...
                   failureAltitudeFt * metersPerFoot, ...
                   goAroundAltitudeFt * metersPerFoot}, ...
    'climb_rate_mps', {-3.0, -3.0, 1.5}, ...
    'left_scale', {0.75, 0.0, 0.0}, ...
    'right_scale', {0.75, 0.75, 0.75}, ...
    'engine_out', {false, true, true});

solutions = cell(1, numel(cases));
messages = strings(1, numel(cases));
searchOptions = findopOptions('DisplayReport', 'off');
for index = 1:numel(cases)
    current = cases(index);
    set_thrust_scale(runtimeModel, current.left_scale, current.right_scale);
    set_param(runtimeModel, 'SimulationCommand', 'update');
    specification = make_opspec( ...
        runtimeModel, current.engine_out, current.climb_rate_mps, ...
        current.altitude_m, targetU);
    specification = seed_known_profile(specification, current, targetU);
    [operatingPoint, report] = findop(runtimeModel, specification, searchOptions);
    messages(index) = string(report.displayShort);
    if contains(lower(report.displayShort), 'could not find a solution')
        error('MultiFlight:TrimNotConverged', ...
            '%s trim did not converge: %s', current.name, report.displayShort);
    end
    solutions{index} = export_solution(operatingPoint, current);
end

result = struct;
result.converged = true;
result.solver = 'findop';
result.model_version = 'beaver_agent_env-runtime-trim-v1';
result.message = char(strjoin(messages, ' | '));
result.initial_state = solutions{1}.state;
result.profiles = struct( ...
    'twin_descent', solutions{1}, ...
    'engine_out_descent', solutions{2}, ...
    'engine_out_climb', solutions{3});
end

function make_trim_inputs(model)
replace_constant(model, 'AileronCmd', 'AileronCmd', 1);
replace_constant(model, 'ElevatorCmd', 'ElevatorCmd', 2);
replace_constant(model, 'RudderCmd', 'RudderCmd', 3);

left = [model '/Throttle_Left'];
right = [model '/Throttle_Right'];
[leftDestinations, leftPosition, leftSignal] = detach_constant(left);
[rightDestinations, ~, rightSignal] = detach_constant(right);
common = [model '/Throttle_Common'];
add_block('simulink/Sources/In1', common, 'Position', leftPosition, 'Port', '4');
ports = get_param(common, 'PortHandles');
destinations = [leftDestinations(:); rightDestinations(:)];
for index = 1:numel(destinations)
    line = add_line(model, ports.Outport, destinations(index), 'autorouting', 'on');
    if index <= numel(leftDestinations) && ~isempty(leftSignal)
        set_param(line, 'Name', leftSignal);
    elseif index > numel(leftDestinations) && ~isempty(rightSignal)
        set_param(line, 'Name', rightSignal);
    end
end
end

function replace_constant(model, oldName, newName, portNumber)
oldBlock = [model '/' oldName];
[destinations, position, signalName] = detach_constant(oldBlock);
newBlock = [model '/' newName];
add_block('simulink/Sources/In1', newBlock, 'Position', position, ...
    'Port', num2str(portNumber));
ports = get_param(newBlock, 'PortHandles');
for index = 1:numel(destinations)
    line = add_line(model, ports.Outport, destinations(index), 'autorouting', 'on');
    if ~isempty(signalName), set_param(line, 'Name', signalName); end
end
end

function [destinations, position, signalName] = detach_constant(block)
position = get_param(block, 'Position');
lines = get_param(block, 'LineHandles');
destinations = get_param(lines.Outport, 'DstPortHandle');
signalName = get_param(lines.Outport, 'Name');
delete_line(lines.Outport);
delete_block(block);
end

function set_thrust_scale(model, leftScale, rightScale)
leftExpression = table_expression(leftScale);
rightExpression = table_expression(rightScale);
set_param([model '/Propulsion_Left/ThrustX'], ...
    'DataSpecification', 'Table and breakpoints', 'Table', leftExpression);
set_param([model '/Propulsion_Right/ThrustX'], ...
    'DataSpecification', 'Table and breakpoints', 'Table', rightExpression);
end

function expression = table_expression(scale)
expression = sprintf(['[0, %.16g*getCoefficient(aircraft,"CX","Propeller",' ...
    'Component="Propeller").Table.Value(2:end)]'], scale);
end

function specification = make_opspec(model, engineOut, climbRate, altitude, targetU)
specification = operspec(model);
for index = 1:numel(specification.States)
    specification.States(index).Known = false(size(specification.States(index).Known));
    specification.States(index).SteadyState = false(size(specification.States(index).SteadyState));
end

specification.States(1).x = 0;
specification.States(1).SteadyState = true;
specification.States(1).Min = -0.20;
specification.States(1).Max = 0.20;
specification.States(2).x = 0.06;
specification.States(2).SteadyState = true;
specification.States(2).Min = -0.20;
specification.States(2).Max = 0.30;
specification.States(3).x = 0;
specification.States(3).Known = true;
specification.States(3).SteadyState = true;

for index = 4:6
    specification.States(index).x = 0;
    specification.States(index).SteadyState = true;
    specification.States(index).Min = -0.15;
    specification.States(index).Max = 0.15;
end

specification.States(7).x = targetU;
specification.States(7).Known = true;
specification.States(7).SteadyState = true;
specification.States(8).x = 0;
specification.States(8).SteadyState = true;
specification.States(8).Min = -8;
specification.States(8).Max = 8;
specification.States(9).x = 1;
specification.States(9).SteadyState = true;
specification.States(9).Min = -8;
specification.States(9).Max = 12;

specification.States(10).x = 0;
specification.States(10).Known = true;
specification.States(11).x = 0;
specification.States(11).SteadyState = true;
specification.States(12).x = -altitude;
specification.States(12).Known = true;
specification.States(12).SteadyState = false;
specification.States(12).dxMin = -climbRate;
specification.States(12).dxMax = -climbRate;

aircraftData = evalin('base', 'aircraft');
for index = 1:numel(specification.Inputs)
    name = get_param(specification.Inputs(index).Block, 'Name');
    switch name
        case 'AileronCmd'
            surface = aircraftData.Surfaces(1).Surfaces(1);
            specification.Inputs(index).u = 0;
            specification.Inputs(index).Min = surface.MinimumValue;
            specification.Inputs(index).Max = surface.MaximumValue;
        case 'ElevatorCmd'
            surface = aircraftData.Surfaces(2).Surfaces(1);
            specification.Inputs(index).u = -0.02;
            specification.Inputs(index).Min = surface.MinimumValue;
            specification.Inputs(index).Max = surface.MaximumValue;
        case 'RudderCmd'
            surface = aircraftData.Surfaces(3).Surfaces(1);
            specification.Inputs(index).u = double(engineOut) * -0.15;
            specification.Inputs(index).Min = surface.MinimumValue;
            specification.Inputs(index).Max = surface.MaximumValue;
        case 'Throttle_Common'
            specification.Inputs(index).u = 0.25 + 0.45 * double(engineOut);
            specification.Inputs(index).Min = 0;
            specification.Inputs(index).Max = 1;
    end
end
end

function specification = seed_known_profile(specification, trimCase, targetU)
if ~trimCase.engine_out
    seed = struct('phi', 0.0136160413039, 'theta', 0.0647610681203, ...
        'aileron', 0.00202547955338, 'elevator', -0.0109658218634, ...
        'rudder', -0.0374364069557, 'throttle', 0.16863024396);
elseif trimCase.climb_rate_mps < 0
    seed = struct('phi', 0.0175700775848, 'theta', 0.0647598704702, ...
        'aileron', 0.000818445603132, 'elevator', -0.0109595158183, ...
        'rudder', -0.0520614487636, 'throttle', 0.207220892838);
else
    seed = struct('phi', 0.0848432053851, 'theta', 0.162303204528, ...
        'aileron', -0.019551264426, 'elevator', -0.00965061067912, ...
        'rudder', -0.299092570837, 'throttle', 0.614702877432);
end

specification.States(1).x = seed.phi;
specification.States(2).x = seed.theta;
specification.States(8).x = 0;
specification.States(9).x = ...
    (-trimCase.climb_rate_mps + sin(seed.theta) * targetU) / ...
    (cos(seed.phi) * cos(seed.theta));
for index = 1:numel(specification.Inputs)
    name = get_param(specification.Inputs(index).Block, 'Name');
    switch name
        case 'AileronCmd'
            specification.Inputs(index).u = seed.aileron;
        case 'ElevatorCmd'
            specification.Inputs(index).u = seed.elevator;
        case 'RudderCmd'
            specification.Inputs(index).u = seed.rudder;
        case 'Throttle_Common'
            specification.Inputs(index).u = seed.throttle;
    end
end
end

function solution = export_solution(operatingPoint, trimCase)
inputValues = struct;
for index = 1:numel(operatingPoint.Inputs)
    inputValues.(get_param(operatingPoint.Inputs(index).Block, 'Name')) = ...
        operatingPoint.Inputs(index).u;
end

states = operatingPoint.States;
solution = struct;
solution.vertical_speed = trimCase.climb_rate_mps / 0.3048;
solution.airspeed = sqrt(states(7).x^2 + states(8).x^2 + states(9).x^2) / 0.3048;
solution.roll = states(1).x;
solution.pitch = states(2).x;
solution.aileron = inputValues.AileronCmd;
solution.elevator = inputValues.ElevatorCmd;
solution.rudder = inputValues.RudderCmd;
if trimCase.engine_out
    solution.throttle_left = 0.0;
else
    solution.throttle_left = inputValues.Throttle_Common;
end
solution.throttle_right = inputValues.Throttle_Common;
solution.state = struct( ...
    'phi', states(1).x, 'theta', states(2).x, 'psi', states(3).x, ...
    'p', states(4).x, 'q', states(5).x, 'r', states(6).x, ...
    'U', states(7).x, 'V', states(8).x, 'W', states(9).x, ...
    'XN', states(10).x, 'YE', states(11).x, 'ZD', states(12).x);
end

function cleanup_runtime_model(model, file)
if bdIsLoaded(model), close_system(model, 0); end
if exist(file, 'file'), delete(file); end
end

function ensure_source_loaded(model)
try
    if ~bdIsLoaded(model), load_system(model); end
catch restoreError
    warning('MultiFlight:ModelRestoreFailed', ...
        'Unable to reload %s after trim: %s', model, restoreError.message);
end
end
