function unit = qmrlab_ci_unit_for(modelId, mapName, era)
%QMRLAB_CI_UNIT_FOR The unit qMRLab produces, which the harness converts from.
%   Declared rather than assumed: the harness refuses an unknown unit instead of
%   defaulting to identity, because a wrong scale publishes plausible wrong numbers.
%
%   ERA matters for exactly one case: v2.0.5's MTSAT_exec returns MTsat as a raw
%   FRACTION, while v3.0.0's mt_sat.m (and the archive's own FitResults, and the
%   canonical unit in models/mt_sat.yml) all use PERCENT. Declaring both 'au' made
%   scale_between() a no-op and published a 100x scale difference as if it were a
%   version-drift finding -- it is a unit convention, not a result. r=1.0 with a
%   ~100x offset is the signature: a rescaling, not a disagreement.
%
%   AUDITED 2026-08-19 (C1, final whole-branch review): every case below was checked
%   against the archive's own FitResults for that model, not assumed. inversion_recovery/T1
%   was found wrong -- declared 's', but the archive's own FitResults/T1.nii.gz has
%   median 762.1 and max 5000.0, which are only plausible as MILLISECONDS (brain T1 at
%   3T is 0.8-1.5 s). That is exactly the mono_t2/T2 case below, and now lives beside it.
%   qmt_spgr/T2f and T2r were re-checked and are CORRECT as declared in seconds despite
%   looking small: free-pool T2f really is ~25 ms (median 0.025 s) and restricted-pool
%   T2r really is ~12 microseconds (median 1.22e-05 s) in this model -- do not "fix" them.
    key = [modelId '/' mapName];
    switch key
        case 'mono_t2/T2';             unit = 'ms';
        case 'inversion_recovery/T1';  unit = 'ms';
        % Both qMT streams, listed explicitly. The switch is keyed on 'model/map', so
        % a missing id here does NOT raise -- it falls through to 'au', and units.py
        % maps ('au','fraction') to 1.0, which would let a Ramani F map through
        % unconverted and unremarked while kr/R1f/R1r failed with an unrelated
        % 'no conversion from au to s^-1'. The sub-model changes how these six are
        % estimated, never what they are, so the units are qmt_spgr's verbatim.
        case {'qmt_spgr/T2f', 'qmt_spgr_ramani/T2f'}; unit = 's';
        case {'qmt_spgr/T2r', 'qmt_spgr_ramani/T2r'}; unit = 's';
        case {'vfa_t1/T1', 'mt_sat/T1'}; unit = 's';
        case 'mt_ratio/MTR'; unit = 'percent';
        case 'mt_sat/MTR';   unit = 'percent';
        case 'mt_sat/MTsat'
            if era == 2
                unit = 'fraction';
            else
                unit = 'percent';
            end
        case {'qmt_spgr/F', 'qmt_spgr_ramani/F'}; unit = 'fraction';
        case {'qmt_spgr/kr','qmt_spgr/R1f','qmt_spgr/R1r', ...
              'qmt_spgr_ramani/kr','qmt_spgr_ramani/R1f','qmt_spgr_ramani/R1r'}
            unit = 's^-1';
        otherwise; unit = 'au';
    end
end
