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

            [times, FitResults] = qmrlab_ci_run_fits_isolated(data, Model, n);

            maps = {};
            resolved = {};
            names = qmrlab_ci_map_names(modelId, 3);
            for jj = 1:numel(names)
                nm = names{jj};
                cands = qmrlab_ci_field_candidates(modelId, nm);
                src = '';
                for kk = 1:numel(cands)
                    if isfield(FitResults, cands{kk}), src = cands{kk}; break; end
                end
                if isempty(src)
                    % Names the fields FitResults ACTUALLY has, not just the ones tried:
                    % the older qMRLab APIs this benchmark also targets may rename them,
                    % and a CI log alone should be enough to diagnose that.
                    error('qmrlab_ci:missingOutput', ...
                          '%s: none of {%s} present in FitResults for map %s; FitResults has {%s}', ...
                          modelId, strjoin(cands, ', '), nm, ...
                          strjoin(fieldnames(FitResults)', ', '));
                end
                if ~strcmp(src, nm)
                    fprintf('  %s/%s <- FitResults.%s\n', modelId, nm, src);
                end
                resolved{end+1} = src;  %#ok<AGROW>
                rel = fullfile('maps', modelId, [nm '.nii.gz']);
                qmrlab_ci_write_nii(fullfile(outRoot, rel), FitResults.(src));
                maps{end+1} = struct('name', nm, ...
                                     'unit', qmrlab_ci_unit_for(modelId, nm, 3), ...
                                     'path', strrep(rel, '\', '/'));  %#ok<AGROW>
            end

            % Falls back to the size of the first map ACTUALLY produced. Using the
            % canonical name here was the bug: for b1_dam/b1_afi/mt_sat the canonical
            % name is not a FitResults field, and those three are exactly the models
            % whose archives ship no Mask, so this is their only path.
            if isfield(data, 'Mask') && ~isempty(data.Mask)
                nVox = nnz(data.Mask);
            else
                nVox = numel(FitResults.(resolved{1}));
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
        % The record write sits OUTSIDE the fit's try/catch and can throw on its own
        % (MATLAB:MKDIR:ExistsAsFile, a full disk). Letting that escape would end the loop
        % and discard every remaining model for this target, breaking the guarantee above
        % that one broken model degrades only itself. Reported on stderr so a CI log shows
        % it, then the sweep continues.
        try
            qmrlab_ci_record(fullfile(outRoot, 'records', [modelId '.json']), record);
        catch werr
            fprintf(2, '%s / %s: record write FAILED (%s: %s) -- continuing\n', ...
                    targetId, modelId, werr.identifier, werr.message);
        end
        fprintf('%s / %s: %s\n', targetId, modelId, record.status);
    end
end

function [times, FitResults] = qmrlab_ci_run_fits_isolated(data, Model, n)
%QMRLAB_CI_RUN_FITS_ISOLATED Repeat FitData(data, Model, 0) from an isolated temp dir.
%
%   qMRLab's FitData writes FitTempResults.mat into the CURRENT directory every 20
%   voxels (Common/FitData.m). v3.0.0 deletes it on a normal completion, but skips
%   that cleanup if FitData throws mid-loop; earlier eras never delete it at all
%   (confirmed: v2.0.5's Common/FitData.m has the identical save with no matching
%   delete). Running from a throwaway temp directory keeps it out of the checkout
%   on every exit path; onCleanup restores the caller's directory and removes the
%   temp one whether the fit finishes, throws, or is interrupted. This mirrors
%   qmrlab_ci_era1.m's qmrlab_ci_era1_run_fits, which needs its own separate copy
%   because V1's FitData takes a different argument list.
    origDir = pwd;
    tmpdir = tempname;
    mkdir(tmpdir);
    cd(tmpdir);
    cleaner = onCleanup(@() qmrlab_ci_restore_dir(origDir, tmpdir));

    times = zeros(1, n);
    for r = 1:n
        t0 = tic;
        FitResults = FitData(data, Model, 0);
        times(r) = toc(t0);
    end
end

function qmrlab_ci_restore_dir(origDir, tmpdir)
%QMRLAB_CI_RESTORE_DIR Return to ORIGDIR and remove TMPDIR. Runs on every exit path.
    cd(origDir);
    qmrlab_ci_rmtmp(tmpdir);
end
