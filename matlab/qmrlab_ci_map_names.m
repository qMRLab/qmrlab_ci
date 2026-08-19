function names = qmrlab_ci_map_names(modelId)
%QMRLAB_CI_MAP_NAMES Canonical output maps per model, matching models/<id>.yml.
    switch modelId
        case 'qmt_spgr';           names = {'F','kr','R1f','R1r','T2f','T2r'};
        case 'inversion_recovery'; names = {'T1'};
        case 'vfa_t1';             names = {'T1','M0'};
        case 'b1_dam';             names = {'B1map'};
        case 'b1_afi';             names = {'B1map'};
        case 'mono_t2';            names = {'T2','M0'};
        case 'mt_ratio';           names = {'MTR'};
        case 'mt_sat';             names = {'MTsat','T1','MTR'};
        otherwise; error('qmrlab_ci:unknownModel', 'no map list for %s', modelId);
    end
end
