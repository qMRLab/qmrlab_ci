function [data, Model] = qmrlab_ci_load_era2(dataRoot, modelId)
%QMRLAB_CI_LOAD_ERA2 Assemble inputs for the CamelCase model classes (v2.0.0-v2.0.5).
%
%   Only five models exist in this era; targets/qmrlab@v2.0.*/target.yml declares
%   exactly those, so an unhandled id here means the declaration and the driver have
%   drifted apart and should fail loudly rather than silently skip.
    switch modelId
        case 'inversion_recovery'
            Model = InversionRecovery;
            data.IRData = qmrlab_ci_load_any(dataRoot, 'ir', 'IRData.mat');
            data.Mask   = qmrlab_ci_load_any(dataRoot, 'ir', 'Mask.mat');
        case 'qmt_spgr'
            Model = SPGR;
            data.MTdata = qmrlab_ci_load_any(dataRoot, 'qmt', 'MTdata.mat');
            data.Mask   = qmrlab_ci_load_any(dataRoot, 'qmt', 'Mask.mat');
            data.R1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'R1map.mat');
            data.B1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B1map.mat');
            data.B0map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B0map.mat');
        case 'vfa_t1'
            Model = VFA_T1;
            % v2.0.5's VFA_T1 (Models/T1_Mapping/VFA_T1.m) declares
            % MRIinputs = {'SPGR','B1map'} -- the field is literally named SPGR in
            % this era. VFAData is v3.0.0's name for the same acquisition; verified
            % by running this loader and reading the class source after it threw
            % "Unrecognized field name 'SPGR'" with the era-3 name.
            data.SPGR    = qmrlab_ci_load_any(dataRoot, 'vfa_t1', 'VFAData.nii.gz');
            data.Mask    = qmrlab_ci_load_any(dataRoot, 'vfa_t1', 'Mask.nii.gz');
            data.B1map   = qmrlab_ci_load_any(dataRoot, 'vfa_t1', 'B1map.nii.gz');
        case 'mt_sat'
            Model = MTSAT;
            data.MTw = qmrlab_ci_load_any(dataRoot, 'mtsat', 'MTw.nii.gz');
            data.PDw = qmrlab_ci_load_any(dataRoot, 'mtsat', 'PDw.nii.gz');
            data.T1w = qmrlab_ci_load_any(dataRoot, 'mtsat', 'T1w.nii.gz');
        case 'b1_dam'
            Model = B1_DAM;
            % v2.0.5's B1_DAM (Models/FieldMaps/B1_DAM.m) declares
            % MRIinputs = {'SF60','SF120'} and computes
            % acos(SF120./(2*SF60))/(60 deg) -- the single- and double-flip-angle
            % SPGR acquisitions at the model's nominal 60 degrees. SFalpha/SF2alpha
            % are v3.0.0's names for the identical two files; verified by running
            % this loader and reading the class source after it threw "Unrecognized
            % field name 'SF120'" with the era-3 names.
            data.SF60  = qmrlab_ci_load_any(dataRoot, 'b1_dam', 'SFalpha.nii.gz');
            data.SF120 = qmrlab_ci_load_any(dataRoot, 'b1_dam', 'SF2alpha.nii.gz');
        otherwise
            error('qmrlab_ci:unknownModel', 'no era-2 loader for %s', modelId);
    end
end
