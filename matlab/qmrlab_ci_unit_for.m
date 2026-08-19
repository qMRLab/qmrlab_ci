function unit = qmrlab_ci_unit_for(modelId, mapName)
%QMRLAB_CI_UNIT_FOR The unit qMRLab produces, which the harness converts from.
%   Declared rather than assumed: the harness refuses an unknown unit instead of
%   defaulting to identity, because a wrong scale publishes plausible wrong numbers.
    key = [modelId '/' mapName];
    switch key
        case 'mono_t2/T2';   unit = 'ms';
        case 'qmt_spgr/T2f'; unit = 's';
        case 'qmt_spgr/T2r'; unit = 's';
        case {'inversion_recovery/T1', 'vfa_t1/T1', 'mt_sat/T1'}; unit = 's';
        case {'mt_ratio/MTR', 'mt_sat/MTR'}; unit = 'percent';
        case 'qmt_spgr/F';   unit = 'fraction';
        case {'qmt_spgr/kr','qmt_spgr/R1f','qmt_spgr/R1r'}; unit = 's^-1';
        otherwise; unit = 'au';
    end
end
