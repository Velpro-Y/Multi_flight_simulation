function finalize_ground_capability_checks(outputDir)
% Reprocess saved logs without rerunning the aircraft model.
names={'static_75','symmetric','reduce_left','reduce_right'};
records=cell(1,4);
for c=1:4
    file=fullfile(outputDir,[names{c} '.json']);
    record=jsondecode(fileread(file)); s=record.summary;
    if c>1
        saved=load(fullfile(outputDir,[names{c} '.mat']),'out'); out=saved.out;
        controls=out.checkControl; state=squeeze(controls.Data);
        if size(state,1)~=numel(controls.Time), state=state'; end
        tt=controls.Time(:); ix=find(state(:,3)>=1,1);
        assert(~isempty(ix),'Aircraft never reached 5kn'); start=tt(ix);
        s.accelerated_to_5kn=true; s.differential_start_s=start;
        s.final_left_throttle=state(end,1); s.final_right_throttle=state(end,2);
        t=out.tout(:); h=rad2deg(unwrap(vec(out.psi)));
        startHeading=interp1(t,h,start);
        s.post_heading_change_deg=h(end)-startHeading;
        for k=1:2
            force=out.get(sprintf('checkForce%d',k));
            values=squeeze(force.Data);
            if size(values,1)~=numel(force.Time), values=values'; end
            s.(sprintf('mean_thrust%d_N',k))=mean(values(force.Time>=start,1));
        end
        s.passed=s.safe && all(isfinite([s.mean_thrust1_N,s.mean_thrust2_N])) && ...
            abs(s.wheel1_min_deg)<0.01 && abs(s.wheel1_max_deg)<0.01;
        record.control=struct('time_s',tt,'throttle_left',state(:,1), ...
            'throttle_right',state(:,2),'phase',state(:,3));
    end
    record.summary=s; records{c}=record;
end
base=records{2}.summary;
% This is a functional direction check, not a minimum aircraft yaw-authority requirement.
threshold=max(0.05,10*abs(base.post_heading_change_deg));
base.passed=base.passed && abs(base.post_heading_change_deg)<2 && ...
    abs(base.mean_thrust1_N-base.mean_thrust2_N)<1;
records{2}.summary=base;
for c=3:4
    s=records{c}.summary;
    if c==3, direction=-1; else, direction=1; end
    s.yaw_relative_to_symmetric_deg=s.post_heading_change_deg-base.post_heading_change_deg;
    s.direction_threshold_deg=threshold;
    s.passed=s.passed && direction*(s.mean_thrust1_N-s.mean_thrust2_N)>0 && ...
        direction*s.yaw_relative_to_symmetric_deg>threshold;
    records{c}.summary=s;
end
summaries=cell(1,4);
for c=1:4
    summaries{c}=records{c}.summary;
    writeJson(fullfile(outputDir,[names{c} '.json']),records{c});
end
passed=all(cellfun(@(s) s.passed,summaries));
writeJson(fullfile(outputDir,'summary.json'),struct('passed',passed,'cases',{summaries}, ...
    'direction_threshold_deg',threshold, ...
    'criterion','Differential yaw relative to symmetric baseline exceeds max(0.05deg,10x baseline drift), with correct measured thrust difference and stable ground contact', ...
    'scope','Static 75 degree and differential thrust functional checks; not maximum-angle rolling or differential-thrust U-turn validation'));
fprintf('FINAL_CHECKS_PASSED=%d\n',passed);
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
