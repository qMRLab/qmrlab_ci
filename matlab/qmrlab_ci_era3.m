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
                cands = qmrlab_ci_field_candidates(modelId, nm);
                src = '';
                for kk = 1:numel(cands)
                    if isfield(FitResults, cands{kk}), src = cands{kk}; break; end
                end
                if isempty(src)
                    error('qmrlab_ci:missingOutput', ...
                          '%s: none of {%s} present in FitResults for map %s', ...
                          modelId, strjoin(cands, ', '), nm);
                end
                if ~strcmp(src, nm)
                    fprintf('  %s/%s <- FitResults.%s\n', modelId, nm, src);
                end
                rel = fullfile('maps', modelId, [nm '.nii.gz']);
                qmrlab_ci_write_nii(fullfile(outRoot, rel), FitResults.(src));
                maps{end+1} = struct('name', nm, ...
                                     'unit', qmrlab_ci_unit_for(modelId, nm), ...
                                     'path', strrep(rel, '\', '/'));  %#ok<AGROW>
            end

            if isfield(data, 'Mask') && ~isempty(data.Mask)
                nVox = nnz(data.Mask);
            else
                nVox = numel(FitResults.(names{1}));
            end

            % jsonencode() writes a 1-element numeric array as a bare scalar, which
            % violates the record schema (repeats must equal numel(fit_seconds)). A cell
            % array always encodes as a JSON array, so the single-repeat case -- which is
            % the CONFIGURED case for qmt_spgr -- round-trips correctly.
            record.timing = struct('repeats', n, 'n_voxels_fitted', nVox);
            record.timing.fit_seconds = num2cell(times);
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
