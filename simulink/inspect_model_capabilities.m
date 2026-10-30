function inspect_model_capabilities
%INSPECT_MODEL_CAPABILITIES Read-only structural report for beaver_agent_env.

thisDir = fileparts(mfilename('fullpath'));
oldDir = pwd;
cleanupDir = onCleanup(@() cd(oldDir)); %#ok<NASGU>
cd(thisDir);

mdl = 'beaver_agent_env';
if bdIsLoaded(mdl), close_system(mdl, 0); end
load_system(mdl);
cleanupModel = onCleanup(@() close_system(mdl, 0)); %#ok<NASGU>

fprintf('MODEL=%s\n', mdl);
fprintf('SOLVER=%s\n', get_param(mdl, 'Solver'));
fprintf('START_TIME=%s\n', get_param(mdl, 'StartTime'));
fprintf('STOP_TIME=%s\n', get_param(mdl, 'StopTime'));

fprintf('\n[TOP_LEVEL_BLOCKS]\n');
blocks = find_system(mdl, 'SearchDepth', 1, 'Type', 'Block');
for k = 2:numel(blocks)
    fprintf('%s | %s\n', get_param(blocks{k}, 'Name'), ...
        get_param(blocks{k}, 'BlockType'));
end

fprintf('\n[ROOT_INPORTS]\n');
inports = find_system(mdl, 'SearchDepth', 1, 'BlockType', 'Inport');
if isempty(inports), fprintf('NONE\n'); end
for k = 1:numel(inports)
    fprintf('%s | Port=%s\n', inports{k}, get_param(inports{k}, 'Port'));
end

fprintf('\n[ROOT_CONSTANTS]\n');
constants = find_system(mdl, 'SearchDepth', 1, 'BlockType', 'Constant');
if isempty(constants), fprintf('NONE\n'); end
for k = 1:numel(constants)
    fprintf('%s | Value=%s\n', constants{k}, get_param(constants{k}, 'Value'));
end

fprintf('\n[EOM_INITIAL_CONDITIONS]\n');
eomCandidates = find_system(mdl, 'LookUnderMasks', 'all', ...
    'FollowLinks', 'on', 'Regexp', 'on', 'Name', '.*6DOF.*Euler.*');
if isempty(eomCandidates), fprintf('NONE\n'); end
for k = 1:numel(eomCandidates)
    block = eomCandidates{k};
    fprintf('BLOCK=%s\n', block);
    dialog = get_param(block, 'DialogParameters');
    if isempty(dialog), continue; end
    names = fieldnames(dialog);
    for n = 1:numel(names)
        key = names{n};
        if contains(lower(key), {'initial','xme','vm','eul','pm','mass','inertia','gravity'})
            try
                fprintf('  %s=%s\n', key, get_param(block, key));
            catch
            end
        end
    end
end

fprintf('\n[ENVIRONMENT_RELATED_BLOCKS]\n');
allBlocks = find_system(mdl, 'LookUnderMasks', 'all', ...
    'FollowLinks', 'on', 'Type', 'Block');
matched = false;
for k = 1:numel(allBlocks)
    path = allBlocks{k};
    if ~isempty(regexpi(path, 'wind|gust|turb|atmos|weather|air data|airspeed'))
        fprintf('%s | %s\n', path, get_param(path, 'BlockType'));
        matched = true;
    end
end
if ~matched, fprintf('NONE\n'); end

fprintf('\n[ENVIRONMENT_MASK_PARAMETERS]\n');
for k = 1:numel(allBlocks)
    path = allBlocks{k};
    if ~isempty(regexpi(path, 'dryden|wind|turb|atmos'))
        try
            maskNames = get_param(path, 'MaskNames');
            maskValues = get_param(path, 'MaskValues');
            for n = 1:min(numel(maskNames), numel(maskValues))
                fprintf('%s | %s=%s\n', path, maskNames{n}, maskValues{n});
            end
        catch
        end
    end
end

fprintf('\n[SELECTED_BASE_VARIABLES]\n');
selectedVars = {'W20','Wdeg','TurbProb','Seed','seed','Wingspan', ...
    'FlapCmd','mass_0','inertia','xme_0','Vm_0','eul_0','pm_0'};
for k = 1:numel(selectedVars)
    name = selectedVars{k};
    try
        value = evalin('base', name);
        fprintf('%s=%s\n', name, mat2str(value));
    catch
        fprintf('%s=UNAVAILABLE\n', name);
    end
end

fprintf('\n[FLAP_RELATED_BLOCKS]\n');
for k = 1:numel(allBlocks)
    path = allBlocks{k};
    if ~isempty(regexpi(path, 'flap'))
        fprintf('%s | %s', path, get_param(path, 'BlockType'));
        try
            fprintf(' | Value=%s', get_param(path, 'Value'));
        catch
        end
        fprintf('\n');
    end
end

fprintf('\n[AERO_AND_PROPULSION_BLOCKS]\n');
for k = 1:numel(allBlocks)
    path = allBlocks{k};
    if ~isempty(regexpi(path, 'aero|propulsion|thrust|coefficient'))
        fprintf('%s | %s\n', path, get_param(path, 'BlockType'));
    end
end

fprintf('\n[REFERENCED_VARIABLES]\n');
try
    vars = Simulink.findVars(mdl);
    names = unique({vars.Name});
    for k = 1:numel(names)
        fprintf('%s\n', names{k});
    end
catch ME
    fprintf('FAILED=%s\n', ME.message);
end

fprintf('\n[MODEL_CALLBACKS]\n');
callbacks = {'PreLoadFcn','InitFcn','StartFcn','StopFcn'};
for k = 1:numel(callbacks)
    try
        value = get_param(mdl, callbacks{k});
        fprintf('%s=%s\n', callbacks{k}, strrep(value, newline, ' '));
    catch ME
        fprintf('%s=UNAVAILABLE (%s)\n', callbacks{k}, ME.message);
    end
end
end
