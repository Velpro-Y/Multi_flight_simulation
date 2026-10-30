function evaluate_twin_trim
%EVALUATE_TWIN_TRIM Compare two physically plausible thrust scalings.
% This creates a disposable trim harness; it does not save the flight model.

thisDir = fileparts(mfilename('fullpath'));
oldDir = pwd;
cleanupDir = onCleanup(@() cd(oldDir));
cd(thisDir);

sourceModel = 'beaver_agent_env';
trimModel = 'beaver_agent_trim_harness';
trimFile = fullfile(thisDir, [trimModel '.slx']);
reportFile = fullfile(thisDir, 'twin_trim_evaluation.txt');
resultFile = fullfile(thisDir, 'twin_trim_evaluation.mat');

if bdIsLoaded(sourceModel), close_system(sourceModel, 0); end
if bdIsLoaded(trimModel), close_system(trimModel, 0); end
load_system(sourceModel);
save_system(sourceModel, trimFile);
close_system(sourceModel, 0);
load_system(trimModel);
cleanupModel = onCleanup(@() close_system(trimModel, 0));

make_trim_inputs(trimModel);
set_param([trimModel '/Propulsion_Left/ThrustX'], 'DataSpecification', 'Table and breakpoints');
set_param([trimModel '/Propulsion_Right/ThrustX'], 'DataSpecification', 'Table and breakpoints');
set_param([trimModel '/Propulsion_Left/ThrustX'], 'Table', ...
    'engineScaleLeft*getCoefficient(aircraft,"CX","Propeller",Component="Propeller").Table.Value');
set_param([trimModel '/Propulsion_Right/ThrustX'], 'Table', ...
    'engineScaleRight*getCoefficient(aircraft,"CX","Propeller",Component="Propeller").Table.Value');
save_system(trimModel);

if exist(reportFile, 'file'), delete(reportFile); end
diary(reportFile);
cleanupDiary = onCleanup(@() diary('off'));
fprintf('Twin-engine trim evaluation\n');
fprintf('Mass = %.6f kg\n', evalin('base', 'state.Mass'));
fprintf('CG = %s m\n', mat2str(evalin('base', 'state.CenterOfGravity'), 8));
fprintf('Inertia = %s kg*m^2\n', mat2str(evalin('base', 'state.Inertia.Variables'), 8));
fprintf('Engine lateral arms: left y=-3.5 m, right y=+3.5 m\n');
fprintf(['Target: altitude 152.4 m, U=45 m/s; evaluate twin descent, ' ...
    'engine-out descent, and engine-out climb.\n\n']);

cases = struct( ...
    'name', {'level_current_double_thrust','level_split_original_thrust', ...
             'level_engine_out_full_engine','climb05_engine_out_full_engine', ...
             'climb15_engine_out_full_engine','level_engine_out_half_engine', ...
             'climb05_engine_out_half_engine','climb15_engine_out_half_engine', ...
             'level_selected_scale075','climb15_engine_out_scale075', ...
             'descent30_twin_scale075','descent30_engine_out_scale075'}, ...
    'scaleLeft', {1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.75, 0.0, 0.75, 0.0}, ...
    'scaleRight',{1.0, 0.5, 1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.75, 0.75, 0.75, 0.75}, ...
    'climbRate', {0.0, 0.0, 0.0, 0.5, 1.5, 0.0, 0.5, 1.5, 0.0, 1.5, -3.0, -3.0}, ...
    'engineOut', {false, false, true, true, true, true, true, true, false, true, false, true}, ...
    'seedIndex', {0, 0, 1, 3, 4, 2, 6, 7, 0, 5, 9, 10});

results = repmat(struct('name','','success',false,'message','', ...
    'inputs',[],'states',[],'op',[],'report',[]), size(cases));
for k = 1:numel(cases)
    c = cases(k);
    fprintf('\n===== CASE %d: %s =====\n', k, c.name);
    fprintf('scaleLeft=%.3f scaleRight=%.3f climbRate=%.3f m/s\n', ...
        c.scaleLeft, c.scaleRight, c.climbRate);
    assignin('base', 'engineScaleLeft', c.scaleLeft);
    assignin('base', 'engineScaleRight', c.scaleRight);
    try
        % Hard-code scales for each compilation so findop cannot reuse a stale
        % lookup table when comparing cases.
        set_param([trimModel '/Propulsion_Left/ThrustX'], 'Table', sprintf( ...
            '%.16g*getCoefficient(aircraft,"CX","Propeller",Component="Propeller").Table.Value', c.scaleLeft));
        set_param([trimModel '/Propulsion_Right/ThrustX'], 'Table', sprintf( ...
            '%.16g*getCoefficient(aircraft,"CX","Propeller",Component="Propeller").Table.Value', c.scaleRight));
        set_param(trimModel, 'SimulationCommand', 'update');
        ops = make_level_opspec(trimModel, c.engineOut, c.climbRate);
        if c.seedIndex > 0 && results(c.seedIndex).success
            ops = seed_opspec(ops, results(c.seedIndex).op);
        end
        [op, opReport] = findop(trimModel, ops);
        success = ~contains(lower(opReport.displayShort), 'could not find a solution');
        if success && ~c.engineOut && c.climbRate == 0
            % Remove the loose trim's bank/sideslip degree of freedom and
            % converge to the symmetric straight-flight solution.
            refined = make_level_opspec(trimModel, false, 0);
            refined = seed_opspec(refined, op);
            refined.States(1).x = 0;
            refined.States(1).Known = true;
            refined.States(8).x = 0;
            refined.States(8).Known = true;
            [opRefined, reportRefined] = findop(trimModel, refined);
            if ~contains(lower(reportRefined.displayShort), 'could not find a solution')
                op = opRefined;
                opReport = reportRefined;
            end
        end
        results(k).name = c.name;
        results(k).op = op;
        results(k).report = opReport;
        results(k).success = ~contains(lower(opReport.displayShort), ...
            'could not find a solution');
        results(k).message = opReport.displayShort;
        results(k).inputs = extract_inputs(op);
        results(k).states = extract_primary_states(op);
        fprintf('%s\n', opReport.displayShort);
        print_solution(op);
    catch ME
        results(k).name = c.name;
        results(k).message = getReport(ME, 'extended', 'hyperlinks', 'off');
        fprintf('FAILED: %s\n', results(k).message);
    end
end

save(resultFile, 'cases', 'results');
fprintf('\nRESULT_FILE=%s\n', resultFile);
fprintf('REPORT_COMPLETE\n');
diary('off');
fprintf('Trim evaluation written to %s\n', reportFile);
end

function ops = seed_opspec(ops, op)
for k = 1:min(numel(ops.States), numel(op.States))
    ops.States(k).x = op.States(k).x;
end
for k = 1:min(numel(ops.Inputs), numel(op.Inputs))
    ops.Inputs(k).u = op.Inputs(k).u;
end
end

function make_trim_inputs(mdl)
replace_constant(mdl, 'AileronCmd', 'AileronCmd', 1);
replace_constant(mdl, 'ElevatorCmd', 'ElevatorCmd', 2);
replace_constant(mdl, 'RudderCmd', 'RudderCmd', 3);

left = [mdl '/Throttle_Left'];
right = [mdl '/Throttle_Right'];
[leftDst, leftPos, leftSignalName] = detach_constant(left);
[rightDst, ~, rightSignalName] = detach_constant(right);
common = [mdl '/Throttle_Common'];
add_block('simulink/Sources/In1', common, 'Position', leftPos, 'Port', '4');
ports = get_param(common, 'PortHandles');
allDst = [leftDst(:); rightDst(:)];
for k = 1:numel(allDst)
    newLine = add_line(mdl, ports.Outport, allDst(k), 'autorouting', 'on');
    if k <= numel(leftDst) && ~isempty(leftSignalName)
        set_param(newLine, 'Name', leftSignalName);
    elseif k > numel(leftDst) && ~isempty(rightSignalName)
        set_param(newLine, 'Name', rightSignalName);
    end
end
end

function replace_constant(mdl, oldName, newName, portNumber)
oldBlock = [mdl '/' oldName];
[dst, pos, signalName] = detach_constant(oldBlock);
newBlock = [mdl '/' newName];
add_block('simulink/Sources/In1', newBlock, 'Position', pos, ...
    'Port', num2str(portNumber));
ports = get_param(newBlock, 'PortHandles');
for k = 1:numel(dst)
    newLine = add_line(mdl, ports.Outport, dst(k), 'autorouting', 'on');
    if ~isempty(signalName), set_param(newLine, 'Name', signalName); end
end
end

function [dst, pos, signalName] = detach_constant(block)
pos = get_param(block, 'Position');
lines = get_param(block, 'LineHandles');
dst = get_param(lines.Outport, 'DstPortHandle');
signalName = get_param(lines.Outport, 'Name');
delete_line(lines.Outport);
delete_block(block);
end

function ops = make_level_opspec(mdl, engineOut, climbRate)
ops = operspec(mdl);
for k = 1:numel(ops.States)
    ops.States(k).Known = false(size(ops.States(k).Known));
    ops.States(k).SteadyState = false(size(ops.States(k).SteadyState));
end

% Euler angles phi, theta, psi.
ops.States(1).x = 0;
ops.States(1).Known = false;
ops.States(1).SteadyState = true;
ops.States(1).Min = -0.20;
ops.States(1).Max = 0.20;
ops.States(2).x = 0.035;
ops.States(2).Known = false;
ops.States(2).SteadyState = true;
ops.States(2).Min = -0.20;
ops.States(2).Max = 0.30;
ops.States(3).x = 0;
ops.States(3).Known = true;
ops.States(3).SteadyState = true;

% Body rates p, q, r.
for idx = 4:6
    ops.States(idx).x = 0;
    ops.States(idx).Known = false;
    ops.States(idx).SteadyState = true;
    ops.States(idx).Min = -0.15;
    ops.States(idx).Max = 0.15;
end

% Body velocities U, V, W. Fix U; allow sideslip only for engine-out trim.
ops.States(7).x = 45;
ops.States(7).Known = true;
ops.States(7).SteadyState = true;
ops.States(8).x = 0;
ops.States(8).Known = false;
ops.States(8).SteadyState = true;
ops.States(8).Min = -8;
ops.States(8).Max = 8;
ops.States(9).x = 1;
ops.States(9).Known = false;
ops.States(9).SteadyState = true;
ops.States(9).Min = -8;
ops.States(9).Max = 12;

% Flat-Earth NED position. Forward position may change. Hold lateral path.
ops.States(10).x = 0;
ops.States(10).Known = true;
ops.States(10).SteadyState = false;
ops.States(11).x = 0;
ops.States(11).Known = false;
ops.States(11).SteadyState = true;
ops.States(12).x = -152.4;
ops.States(12).Known = true;
if climbRate == 0
    ops.States(12).SteadyState = true;
else
    ops.States(12).SteadyState = false;
    ops.States(12).dxMin = -climbRate;
    ops.States(12).dxMax = -climbRate;
end

aircraftData = evalin('base', 'aircraft');
for k = 1:numel(ops.Inputs)
    name = get_param(ops.Inputs(k).Block, 'Name');
    switch name
        case 'AileronCmd'
            surf = aircraftData.Surfaces(1).Surfaces(1);
            ops.Inputs(k).u = 0;
            ops.Inputs(k).Known = false;
            ops.Inputs(k).Min = surf.MinimumValue;
            ops.Inputs(k).Max = surf.MaximumValue;
        case 'ElevatorCmd'
            surf = aircraftData.Surfaces(2).Surfaces(1);
            ops.Inputs(k).u = -0.05;
            ops.Inputs(k).Known = false;
            ops.Inputs(k).Min = surf.MinimumValue;
            ops.Inputs(k).Max = surf.MaximumValue;
        case 'RudderCmd'
            surf = aircraftData.Surfaces(3).Surfaces(1);
            ops.Inputs(k).u = engineOut * -0.15;
            ops.Inputs(k).Known = false;
            ops.Inputs(k).Min = surf.MinimumValue;
            ops.Inputs(k).Max = surf.MaximumValue;
        case 'Throttle_Common'
            ops.Inputs(k).u = 0.5 + 0.4 * engineOut;
            ops.Inputs(k).Known = false;
            ops.Inputs(k).Min = 0;
            ops.Inputs(k).Max = 1;
    end
end
end

function data = extract_inputs(op)
data = struct;
for k = 1:numel(op.Inputs)
    data.(get_param(op.Inputs(k).Block, 'Name')) = op.Inputs(k).u;
end
end

function data = extract_primary_states(op)
labels = {'phi','theta','psi','p','q','r','U','V','W','XN','YE','ZD'};
data = struct;
for k = 1:12
    data.(labels{k}) = op.States(k).x;
end
end

function print_solution(op)
fprintf('Inputs:\n');
for k = 1:numel(op.Inputs)
    fprintf('  %s = %.12g\n', get_param(op.Inputs(k).Block, 'Name'), op.Inputs(k).u);
end
labels = {'phi','theta','psi','p','q','r','U','V','W','XN','YE','ZD'};
fprintf('Primary states:\n');
for k = 1:12
    fprintf('  %s = %.12g\n', labels{k}, op.States(k).x);
end
end
