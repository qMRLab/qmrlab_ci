function qmrlab_ci_era1(dataRoot, outRoot, targetId, qmrlabVersion, matlabRelease, models, repeatsJson)
%QMRLAB_CI_ERA1 Drive qMTLab V1 headless.
%
%   V1 predates the model-object API: FitData takes (data, Prot, FitOpt, Method, wait)
%   rather than a model that carries all three. It contributes the two qMT streams and
%   nothing else -- qmt_spgr (SledPikeRP) and qmt_spgr_ramani (Ramani), which are one
%   FitOpt field apart (see qmrlab_ci_era1_protocol).
%
%   MODELS is looped over exactly as in eras 2 and 3, and for their reason: a model
%   that throws is recorded as status 'failed' and the remaining models still run, so
%   one broken stream cannot discard the other. Which ids V1 actually supports is
%   qmrlab_ci_era1_protocol's switch to decide, not this loop's -- the era-2 and era-3
%   loaders own that check for their eras too, and duplicating it here would leave two
%   lists to keep in step.
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
            [Prot, FitOpt] = qmrlab_ci_era1_protocol(modelId);

            data.MTdata = qmrlab_ci_load_any(dataRoot, 'qmt', 'MTdata.mat');
            data.Mask   = qmrlab_ci_load_any(dataRoot, 'qmt', 'Mask.mat');
            data.R1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'R1map.mat');
            data.B1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B1map.mat');
            data.B0map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B0map.mat');

            if size(data.MTdata, ndims(data.MTdata)) ~= numel(Prot.Angles)
                error('qmrlab_ci:protocolMismatch', ...
                      'MTdata has %d points, protocol declares %d', ...
                      size(data.MTdata, ndims(data.MTdata)), numel(Prot.Angles));
            end

            [times, Fit] = qmrlab_ci_era1_run_fits(data, Prot, FitOpt, n);

            % V1 returns F, kf, kr, R1f, R1r, T2f, T2r, resnorm -- the same names later
            % versions produce. Resolved through qmrlab_ci_field_candidates rather than
            % assumed, so a surprise fails loudly instead of silently writing the wrong map.
            maps = {};
            resolved = {};
            names = qmrlab_ci_map_names(modelId, 1);
            for jj = 1:numel(names)
                nm = names{jj};
                cands = qmrlab_ci_field_candidates(modelId, nm);
                src = '';
                for kk = 1:numel(cands)
                    if isfield(Fit, cands{kk}), src = cands{kk}; break; end
                end
                if isempty(src)
                    error('qmrlab_ci:missingOutput', ...
                          '%s: none of {%s} present in Fit for map %s; Fit has {%s}', ...
                          modelId, strjoin(cands, ', '), nm, strjoin(fieldnames(Fit)', ', '));
                end
                if ~strcmp(src, nm)
                    fprintf('  %s/%s <- Fit.%s\n', modelId, nm, src);
                end
                resolved{end+1} = src;  %#ok<AGROW>
                rel = fullfile('maps', modelId, [nm '.nii.gz']);
                qmrlab_ci_write_nii(fullfile(outRoot, rel), Fit.(src));
                maps{end+1} = struct('name', nm, ...
                                     'unit', qmrlab_ci_unit_for(modelId, nm, 1), ...
                                     'path', strrep(rel, '\', '/'));  %#ok<AGROW>
            end

            % Falls back to the size of the first map ACTUALLY produced, never the
            % canonical name, matching era 3's fix for the same fallback.
            if isfield(data, 'Mask') && ~isempty(data.Mask)
                nVox = nnz(data.Mask);
            else
                nVox = numel(Fit.(resolved{1}));
            end

            % jsonencode() writes a 1-element numeric array as a bare scalar, which
            % violates the record schema (repeats must equal numel(fit_seconds)). A cell
            % array always encodes as a JSON array, so the single-repeat case -- which is
            % the CONFIGURED case for both qMT streams -- round-trips correctly.
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
        % it, then the sweep continues. Mirrors eras 2 and 3, and started mattering here
        % the moment V1 stopped contributing exactly one model.
        try
            qmrlab_ci_record(fullfile(outRoot, 'records', [modelId '.json']), record);
        catch werr
            fprintf(2, '%s / %s: record write FAILED (%s: %s) -- continuing\n', ...
                    targetId, modelId, werr.identifier, werr.message);
        end
        fprintf('%s / %s: %s\n', targetId, modelId, record.status);
    end
end

function [times, Fit] = qmrlab_ci_era1_run_fits(data, Prot, FitOpt, n)
%QMRLAB_CI_ERA1_RUN_FITS Repeat V1's FitData from an isolated temp directory.
%
%   V1's FitData writes FitTempResults.mat into the CURRENT directory every 20
%   voxels (Common/FitData.m) -- there is no argument to redirect it, and
%   in CI the current directory is the checkout, so left alone it litters the repo
%   and could end up inside an uploaded results artifact. Running from a throwaway
%   temp directory keeps it out of the checkout entirely; onCleanup restores the
%   caller's directory and deletes the temp one on every exit path, including a fit
%   that throws mid-loop, so one failed repeat cannot strand later models in the
%   wrong directory.
    origDir = pwd;
    tmpdir = tempname;
    mkdir(tmpdir);
    cd(tmpdir);
    cleaner = onCleanup(@() qmrlab_ci_era1_restore(origDir, tmpdir));

    times = zeros(1, n);
    for r = 1:n
        % evalc captures the fit's stdout so it never reaches the CI log. qMRLab prints
        % one "Fitting voxel k/N" line PER VOXEL -- 4101 lines for a single V1 model, 86%
        % of that job's log. Beyond the noise, those writes land inside the timed region,
        % so without this the published fit_seconds partly measures the CI log pipe
        % rather than the fit.
        t0 = tic;
        evalc('Fit = FitData(data, Prot, FitOpt, ''SPGR'', 0);');
        times(r) = toc(t0);
    end
end

function qmrlab_ci_era1_restore(origDir, tmpdir)
%QMRLAB_CI_ERA1_RESTORE Return to ORIGDIR and remove TMPDIR. Runs on every exit path.
    cd(origDir);
    qmrlab_ci_rmtmp(tmpdir);
end
