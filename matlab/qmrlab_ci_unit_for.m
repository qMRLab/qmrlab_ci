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
    key = [modelId '/' mapName];
    switch key
        case 'mono_t2/T2';   unit = 'ms';
        case 'qmt_spgr/T2f'; unit = 's';
        case 'qmt_spgr/T2r'; unit = 's';
        case {'inversion_recovery/T1', 'vfa_t1/T1', 'mt_sat/T1'}; unit = 's';
        case 'mt_ratio/MTR'; unit = 'percent';
        case 'mt_sat/MTR';   unit = 'percent';
        case 'mt_sat/MTsat'
            if era == 2
                unit = 'fraction';
            else
                unit = 'percent';
            end
        case 'qmt_spgr/F';   unit = 'fraction';
        case {'qmt_spgr/kr','qmt_spgr/R1f','qmt_spgr/R1r'}; unit = 's^-1';
        otherwise; unit = 'au';
    end
end
