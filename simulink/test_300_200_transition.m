function test_300_200_transition
%TEST_300_200_TRANSITION Validate the full 500/300/200/500 ft scenario.

thisDir = fileparts(mfilename('fullpath'));
oldDir = pwd;
cleanupDir = onCleanup(@() cd(oldDir)); %#ok<NASGU>
cd(thisDir);

mdl = 'beaver_agent_env';
data = load(fullfile(thisDir, 'twin_trim_parameters.mat'), 'params');
params = data.params;
twin = params.descent;
engineOutDescent = params.engineOutDescent30;
engineOutClimb = params.engineOutClimb15;

failureAltitude = 91.44;
goAroundAltitude = 60.96;
targetAltitude = 152.4;
mToFt = 3.280839895013123;
stepTime = 1.0;
transitionTime = 6.0;
maxSteps = 180;

if bdIsLoaded(mdl), close_system(mdl, 0); end
load_system(mdl);
cleanupModel = onCleanup(@() close_system(mdl, 0)); %#ok<NASGU>
evalin('base', '[aircraft, state] = astDehavillandBeaver();');
evalin('base', ['thrustX = getCoefficient(aircraft,"CX","Propeller",' ...
    'Component="Propeller");']);

state = struct( ...
    'altitude', targetAltitude, ...
    'airspeed', norm([twin.state.U twin.state.V twin.state.W]), ...
    'vertical_speed', -3.0, ...
    'roll', twin.state.phi, ...
    'pitch', twin.state.theta, ...
    'roll_rate', twin.state.p, ...
    'pitch_rate', twin.state.q, ...
    'yaw_rate', twin.state.r);

phase = "TWIN_DESCENT";
goAroundTime = 0.0;
previous = struct( ...
    'aileron', engineOutDescent.control.aileron_rad, ...
    'elevator', engineOutDescent.control.elevator_rad, ...
    'rudder', engineOutDescent.control.rudder_rad, ...
    'throttle', engineOutDescent.control.throttleRight);

timeLog = nan(maxSteps, 1);
altitudeLog = nan(maxSteps, 1);
airspeedLog = nan(maxSteps, 1);
verticalSpeedLog = nan(maxSteps, 1);
rollLog = nan(maxSteps, 1);
pitchLog = nan(maxSteps, 1);
rollRateLog = nan(maxSteps, 1);
pitchRateLog = nan(maxSteps, 1);
yawRateLog = nan(maxSteps, 1);
eventLog = strings(maxSteps, 1);
phaseLog = strings(maxSteps, 1);
aileronLog = nan(maxSteps, 1);
elevatorLog = nan(maxSteps, 1);
rudderLog = nan(maxSteps, 1);
throttleLeftLog = nan(maxSteps, 1);
throttleRightLog = nan(maxSteps, 1);

xFinal = [];
currentTime = 0.0;
failureTime = NaN;
failureCrossingAltitude = NaN;
goAroundStartTime = NaN;
goAroundCrossingAltitude = NaN;
successTime = NaN;

for k = 1:maxSteps
    phaseAtStepStart = phase;
    if phaseAtStepStart == "TWIN_DESCENT"
        control = struct( ...
            'aileron', twin.control.aileron_rad, ...
            'elevator', twin.control.elevator_rad, ...
            'rudder', twin.control.rudder_rad, ...
            'throttleLeft', twin.control.throttleLeft, ...
            'throttleRight', twin.control.throttleRight);
    else
        [control, previous] = scheduled_controller( ...
            state, previous, phaseAtStepStart == "GO_AROUND", ...
            goAroundTime, transitionTime, engineOutDescent, engineOutClimb);
    end

    nextTime = currentTime + stepTime;
    simIn = Simulink.SimulationInput(mdl);
    simIn = simIn.setModelParameter('StartTime', num2str(currentTime), ...
        'StopTime', num2str(nextTime));
    simIn = simIn.setVariable('AileronCmd', control.aileron);
    simIn = simIn.setVariable('ElevatorCmd', control.elevator);
    simIn = simIn.setVariable('RudderCmd', control.rudder);
    simIn = simIn.setVariable('Throttle_Left', control.throttleLeft);
    simIn = simIn.setVariable('Throttle_Right', control.throttleRight);
    if isempty(xFinal)
        eom = [mdl '/6DOF EOM/6DOF (Euler Angles)'];
        simIn = simIn.setBlockParameter(eom, 'xme_0', ...
            mat2str([twin.state.XN twin.state.YE twin.state.ZD], 15));
        simIn = simIn.setBlockParameter(eom, 'Vm_0', ...
            mat2str([twin.state.U twin.state.V twin.state.W], 15));
        simIn = simIn.setBlockParameter(eom, 'eul_0', ...
            mat2str([twin.state.phi twin.state.theta twin.state.psi], 15));
        simIn = simIn.setBlockParameter(eom, 'pm_0', ...
            mat2str([twin.state.p twin.state.q twin.state.r], 15));
    else
        simIn = simIn.setInitialState(xFinal);
    end

    previousAltitude = state.altitude;
    simOut = sim(simIn);
    xFinal = simOut.xFinal;
    currentTime = nextTime;
    if phaseAtStepStart == "GO_AROUND"
        goAroundTime = goAroundTime + stepTime;
    end

    state = read_state(simOut, previousAltitude, stepTime);
    event = "NORMAL";
    if phase == "TWIN_DESCENT" && state.altitude <= failureAltitude
        phase = "ENGINE_OUT_DESCENT";
        event = "LEFT_ENGINE_FAILURE";
        failureTime = currentTime;
        failureCrossingAltitude = state.altitude;
        previous = struct( ...
            'aileron', engineOutDescent.control.aileron_rad, ...
            'elevator', engineOutDescent.control.elevator_rad, ...
            'rudder', engineOutDescent.control.rudder_rad, ...
            'throttle', engineOutDescent.control.throttleRight);
    elseif phase == "ENGINE_OUT_DESCENT" && state.altitude <= goAroundAltitude
        phase = "GO_AROUND";
        event = "GO_AROUND_INITIATED";
        goAroundTime = 0.0;
        goAroundStartTime = currentTime;
        goAroundCrossingAltitude = state.altitude;
    elseif phase == "ENGINE_OUT_DESCENT"
        event = "SINGLE_ENGINE_DESCENT";
    elseif phase == "GO_AROUND"
        event = "SINGLE_ENGINE_GO_AROUND";
    end

    if phase == "GO_AROUND" && state.altitude >= targetAltitude
        phase = "SUCCESS";
        event = "GO_AROUND_SUCCESS";
        successTime = currentTime;
    end

    timeLog(k) = currentTime;
    altitudeLog(k) = state.altitude;
    airspeedLog(k) = state.airspeed;
    verticalSpeedLog(k) = state.vertical_speed;
    rollLog(k) = state.roll;
    pitchLog(k) = state.pitch;
    rollRateLog(k) = state.roll_rate;
    pitchRateLog(k) = state.pitch_rate;
    yawRateLog(k) = state.yaw_rate;
    eventLog(k) = event;
    phaseLog(k) = phase;
    aileronLog(k) = control.aileron;
    elevatorLog(k) = control.elevator;
    rudderLog(k) = control.rudder;
    throttleLeftLog(k) = control.throttleLeft;
    throttleRightLog(k) = control.throttleRight;

    if phase == "SUCCESS"
        break;
    end
end

assert(phase == "SUCCESS", 'Scenario did not reach 500 ft within %d steps.', maxSteps);
used = 1:k;
telemetry = table(timeLog(used), altitudeLog(used) * mToFt, ...
    airspeedLog(used) * mToFt, verticalSpeedLog(used) * mToFt, ...
    rollLog(used), pitchLog(used), ...
    rollRateLog(used), pitchRateLog(used), yawRateLog(used), ...
    eventLog(used), phaseLog(used), aileronLog(used), elevatorLog(used), ...
    rudderLog(used), throttleLeftLog(used), throttleRightLog(used), ...
    'VariableNames', {'time','altitude','airspeed','vertical_speed','roll', ...
    'pitch','roll_rate','pitch_rate','yaw_rate','event','flight_phase', ...
    'aileron','elevator','rudder','throttle_left','throttle_right'});

csvFile = fullfile(thisDir, 'transition_300_200_validation.csv');
reportFile = fullfile(thisDir, 'transition_300_200_validation.txt');
writetable(telemetry, csvFile);

failureIndex = find(telemetry.event == "LEFT_ENGINE_FAILURE", 1);
goAroundIndex = find(telemetry.event == "GO_AROUND_INITIATED", 1);
singleDescentRange = failureIndex:goAroundIndex;
goAroundRange = goAroundIndex:height(telemetry);

metrics = struct;
metrics.failureTime_s = failureTime;
metrics.failureAltitude_ft = failureCrossingAltitude * mToFt;
metrics.goAroundTime_s = goAroundStartTime;
metrics.goAroundAltitude_ft = goAroundCrossingAltitude * mToFt;
metrics.engineOutDescentDuration_s = goAroundStartTime - failureTime;
metrics.successTime_s = successTime;
metrics.minAirspeed_fps = min(telemetry.airspeed);
metrics.maxAbsRoll_rad = max(abs(telemetry.roll));
metrics.singleDescentMeanVerticalSpeed_fps = ...
    mean(telemetry.vertical_speed(singleDescentRange));
metrics.singleDescentMaxAbsRoll_rad = ...
    max(abs(telemetry.roll(singleDescentRange)));
metrics.goAroundMeanVerticalSpeed_fps = ...
    mean(telemetry.vertical_speed(goAroundRange));
metrics.goAroundMaxAbsRoll_rad = max(abs(telemetry.roll(goAroundRange)));

% One simulation step is 1 s, so a roughly 10 ft altitude crossing tolerance
% is expected at the -9.84 ft/s descent rate.
assert(abs(metrics.failureAltitude_ft - failureAltitude * mToFt) <= 3.5 * mToFt, ...
    'Engine failure did not occur within one-step altitude tolerance.');
assert(abs(metrics.goAroundAltitude_ft - goAroundAltitude * mToFt) <= 3.5 * mToFt, ...
    'Go-around did not occur within one-step altitude tolerance.');
assert(metrics.minAirspeed_fps >= 40.0 * mToFt, ...
    'Airspeed fell below the validation safety floor.');
assert(metrics.maxAbsRoll_rad <= 0.35, ...
    'Roll angle exceeded the validation safety bound.');

fid = fopen(reportFile, 'w');
assert(fid >= 0, 'Unable to open report file.');
cleanupFile = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '300 ft failure / 200 ft go-around transition validation\n');
fprintf(fid, 'Failure: t=%.3f s, altitude=%.6f ft\n', ...
    metrics.failureTime_s, metrics.failureAltitude_ft);
fprintf(fid, 'Go-around: t=%.3f s, altitude=%.6f ft\n', ...
    metrics.goAroundTime_s, metrics.goAroundAltitude_ft);
fprintf(fid, 'Single-engine descent duration=%.3f s\n', ...
    metrics.engineOutDescentDuration_s);
fprintf(fid, 'Success: t=%.3f s\n', metrics.successTime_s);
fprintf(fid, 'Minimum airspeed=%.6f ft/s\n', metrics.minAirspeed_fps);
fprintf(fid, 'Maximum absolute roll=%.6f rad\n', metrics.maxAbsRoll_rad);
fprintf(fid, 'Single-engine descent mean vertical speed=%.6f ft/s\n', ...
    metrics.singleDescentMeanVerticalSpeed_fps);
fprintf(fid, 'Single-engine descent maximum absolute roll=%.6f rad\n', ...
    metrics.singleDescentMaxAbsRoll_rad);
fprintf(fid, 'Go-around mean vertical speed=%.6f ft/s\n', ...
    metrics.goAroundMeanVerticalSpeed_fps);
fprintf(fid, 'Go-around maximum absolute roll=%.6f rad\n', ...
    metrics.goAroundMaxAbsRoll_rad);

fprintf('VALIDATION_CSV=%s\n', csvFile);
fprintf('VALIDATION_REPORT=%s\n', reportFile);
fprintf('FAILURE_TIME_S=%.12g\n', metrics.failureTime_s);
fprintf('FAILURE_ALTITUDE_FT=%.12g\n', metrics.failureAltitude_ft);
fprintf('GO_AROUND_TIME_S=%.12g\n', metrics.goAroundTime_s);
fprintf('GO_AROUND_ALTITUDE_FT=%.12g\n', metrics.goAroundAltitude_ft);
fprintf('SUCCESS_TIME_S=%.12g\n', metrics.successTime_s);
fprintf('MIN_AIRSPEED_FPS=%.12g\n', metrics.minAirspeed_fps);
fprintf('MAX_ABS_ROLL_RAD=%.12g\n', metrics.maxAbsRoll_rad);
end

function [control, previous] = scheduled_controller(state, previous, ...
    goAround, goAroundTime, transitionTime, descentTrim, climbTrim)

blend = 0.0;
if goAround
    blend = clamp(goAroundTime / transitionTime, 0.0, 1.0);
end
schedule = interpolate_trim(descentTrim, climbTrim, blend);

rollError = state.roll - schedule.roll;
pCommand = clamp(-1.20 * rollError, -0.12, 0.12);
deltaP = 1.40 * (pCommand - state.roll_rate);
deltaR = 1.40 * (0.0 - state.yaw_rate);
deltaAileron = (-1.7955 * deltaP + 1.033 * deltaR) / 2.217;
deltaRudder = (-0.5425 * deltaP - 0.923 * deltaR) / 2.217;

rawAileron = clamp(schedule.aileron + deltaAileron, -0.25, 0.25);
rawRudder = clamp(schedule.rudder + deltaRudder, -0.50, 0.15);
control.aileron = clamp(rawAileron, previous.aileron - 0.04, ...
    previous.aileron + 0.04);
control.rudder = clamp(rawRudder, previous.rudder - 0.05, ...
    previous.rudder + 0.05);

targetPitch = schedule.pitch ...
    + 0.025 * (schedule.verticalSpeed - state.vertical_speed) ...
    + 0.010 * (schedule.airspeed - state.airspeed);
targetPitch = clamp(targetPitch, 0.04, 0.21);
qCommand = clamp(0.65 * (targetPitch - state.pitch), -0.08, 0.08);
rawElevator = clamp(schedule.elevator ...
    - 0.34 * (qCommand - state.pitch_rate), -0.05, 0.03);
control.elevator = clamp(rawElevator, previous.elevator - 0.012, ...
    previous.elevator + 0.012);

rawThrottle = clamp(schedule.throttle ...
    + 0.020 * (schedule.airspeed - state.airspeed) ...
    + 0.012 * (schedule.verticalSpeed - state.vertical_speed), 0.12, 0.78);
control.throttleRight = clamp(rawThrottle, previous.throttle - 0.06, ...
    previous.throttle + 0.06);
control.throttleLeft = 0.0;

previous.aileron = control.aileron;
previous.elevator = control.elevator;
previous.rudder = control.rudder;
previous.throttle = control.throttleRight;
end

function schedule = interpolate_trim(startTrim, endTrim, blend)
schedule.verticalSpeed = startTrim.targetVerticalSpeed_mps + blend * ...
    (endTrim.targetClimbRate_mps - startTrim.targetVerticalSpeed_mps);
schedule.airspeed = norm([startTrim.state.U startTrim.state.V startTrim.state.W]) + blend * ...
    (norm([endTrim.state.U endTrim.state.V endTrim.state.W]) - ...
    norm([startTrim.state.U startTrim.state.V startTrim.state.W]));
schedule.roll = startTrim.state.phi + blend * ...
    (endTrim.state.phi - startTrim.state.phi);
schedule.pitch = startTrim.state.theta + blend * ...
    (endTrim.state.theta - startTrim.state.theta);
schedule.aileron = startTrim.control.aileron_rad + blend * ...
    (endTrim.control.aileron_rad - startTrim.control.aileron_rad);
schedule.elevator = startTrim.control.elevator_rad + blend * ...
    (endTrim.control.elevator_rad - startTrim.control.elevator_rad);
schedule.rudder = startTrim.control.rudder_rad + blend * ...
    (endTrim.control.rudder_rad - startTrim.control.rudder_rad);
schedule.throttle = startTrim.control.throttleRight + blend * ...
    (endTrim.control.throttleRight - startTrim.control.throttleRight);
end

function state = read_state(simOut, previousAltitude, stepTime)
state.altitude = -double(simOut.Ze.Data(end));
u = double(simOut.u.Data(end));
v = double(simOut.v.Data(end));
w = double(simOut.w.Data(end));
state.airspeed = sqrt(u^2 + v^2 + w^2);
state.vertical_speed = (state.altitude - previousAltitude) / stepTime;
state.roll = double(simOut.phi.Data(end));
state.pitch = double(simOut.theta.Data(end));
state.roll_rate = double(simOut.p.Data(end));
state.pitch_rate = double(simOut.q.Data(end));
state.yaw_rate = double(simOut.r.Data(end));
end

function value = clamp(value, lower, upper)
value = min(max(value, lower), upper);
end
