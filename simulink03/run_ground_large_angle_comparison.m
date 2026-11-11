function run_ground_large_angle_comparison(outputDir,angles,rate)
% Progressive right U-turn comparisons; one MATLAB session, no Agent calls.
if ~exist(outputDir,'dir'), mkdir(outputDir); end
if nargin<2, angles=[20 40 60 75]; end
if nargin<3, rate=15; end
policies={'offset','inner_idle'};
rows={}; stop=false;
for angle=angles
    for p=1:2
        caseId=sprintf('angle%d_%s',angle,policies{p});
        folder=fullfile(outputDir,caseId); mkdir(folder);
        req=struct('nose_wheel_deg',angle,'large_angle_test',true, ...
            'thrust_policy',policies{p},'differential_throttle',0,'steering_rate_deg_s',rate);
        requestFile=fullfile(folder,'request.json');
        resultFile=fullfile(folder,'simulation.json');
        writeJson(requestFile,req);
        previous=pwd; cleanup=onCleanup(@() cd(previous)); cd(folder);
        try
            run_ground_uturn_demo(requestFile,resultFile);
            sim=jsondecode(fileread(resultFile));
            sim=rmfield(sim,{'trajectory','control'});
            sim.case_id=caseId;
            sim.actual_target_angle_reached=sim.max_actual_front_wheel_angle_deg>=angle-0.1;
            sim.angle_case_passed=sim.passed && sim.actual_target_angle_reached;
            if ~sim.safe, stop=true; end
        catch exception
            sim=struct('case_id',caseId,'angle_case_passed',false,'error',exception.message);
            stop=true;
        end
        rows{end+1}=sim;
        writeJson(fullfile(outputDir,'summary.json'),struct('cases',{rows}, ...
            'stopped_after_unsafe_case',stop, ...
            'steering_rate_deg_s',rate, ...
            'note','Right turns, maximum angle held until 150deg heading; both policies share identical settings. 177deg is the Demo completion threshold. inner_idle means zero modeled thrust, not calibrated real idle.'));
        fprintf('CASE %s %s\n',caseId,jsonencode(sim));
        clear cleanup;
    end
    if stop, break; end
end
end

function writeJson(path,value)
fid=fopen(path,'w'); assert(fid>=0); cleanup=onCleanup(@() fclose(fid));
fprintf(fid,'%s',jsonencode(value));
end
