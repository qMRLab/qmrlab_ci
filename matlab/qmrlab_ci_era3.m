function qmrlab_ci_era3(dataRoot, outRoot, targetId, qmrlabVersion, matlabRelease, models, repeatsJson)
%QMRLAB_CI_ERA3 Drive the snake_case object API (qMRLab v2.1.0+ and master).
%
%   MODELS is a cellstr of canonical model ids. Each is fitted against the canonical
%   input tree at DATAROOT and written under OUTROOT. A model that throws is recorded
%   as status 'failed' and the remaining models still run: one broken model must not
%   discard a whole target's results.
    repeats = jsondecode(repeatsJson);
    env = struct( ...
        'matlab_release', matlabRelease, ...
        'runner_os', getenv('RUNNER_OS'), ...
        'harness_commit', getenv('GITHUB_SHA'), ...
        'run_started_utc', getenv('QMRLAB_CI_RUN_STARTED'));

    for ii = 1:numel(models)
        modelId = models{ii};
        n = qmrlab_ci_repeats_for(repeats, modelId);
        record = struct('target', targetId, 'software', 'qmrlab', ...
                        'version', qmrlabVersion, 'model', modelId, 'status', 'ok', ...
                        'environment', env, 'timing', struct(), 'maps', {{}});
        try
            [data, Model] = qmrlab_ci_load_era3(dataRoot, modelId);

            times = zeros(1, n);
            for r = 1:n
                t0 = tic;
                FitResults = FitData(data, Model, 0);
                times(r) = toc(t0);
            end

            maps = {};
            names = qmrlab_ci_map_names(modelId);
            for jj = 1:numel(names)
                nm = names{jj};
                rel = fullfile('maps', modelId, [nm '.nii.gz']);
                qmrlab_ci_write_nii(fullfile(outRoot, rel), FitResults.(nm));
                maps{end+1} = struct('name', nm, ...
                                     'unit', qmrlab_ci_unit_for(modelId, nm), ...
                                     'path', strrep(rel, '\', '/'));  %#ok<AGROW>
            end

            if isfield(data, 'Mask') && ~isempty(data.Mask)
                nVox = nnz(data.Mask);
            else
                nVox = numel(FitResults.(names{1}));
            end

            record.timing = struct('repeats', n, 'fit_seconds', times, ...
                                   'n_voxels_fitted', nVox);
            record.maps = maps;
        catch err
            record.status = 'failed';
            record.error = sprintf('%s: %s', err.identifier, err.message);
            record.timing = struct();
            record.maps = {};
        end
        qmrlab_ci_record(fullfile(outRoot, 'records', [modelId '.json']), record);
        fprintf('%s / %s: %s\n', targetId, modelId, record.status);
    end
end
