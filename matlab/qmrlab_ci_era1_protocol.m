function [Prot, FitOpt] = qmrlab_ci_era1_protocol()
%QMRLAB_CI_ERA1_PROTOCOL The canonical qMT protocol, in V1's struct shape.
%
%   Transcribed from qMRLab v3.0.0 src/Models/Magnetization_transfer/qmt_spgr.m --
%   its default Prot.MTdata.Mat, Prot.TimingTable.Mat, and buttons defaults -- because
%   the benchmark only means anything if V1 is asked the same question as every other
%   target. V1's own SPGR/Parameters/DefaultProt.mat is NOT used: it declares 15
%   measurement points for a dataset that has 10, plus a different TR and model.
%
%   If V1's numbers look wrong, this function is the first suspect.

    % Ten (angle, offset) pairs, in acquisition order.
    Prot.Angles  = [142; 426; 142; 426; 142; 426; 142; 426; 142; 426];
    Prot.Offsets = [443; 443; 1088; 1088; 2732; 2732; 6862; 6862; 17235; 17235];

    % Timing, seconds. TR is the sum of the other four, which is the invariant
    % qmt_spgr.m re-imposes in UpdateFields.
    Prot.Tm = 0.0102;   % MT pulse duration
    Prot.Ts = 0.0030;   % free precession, MT pulse -> excitation
    Prot.Tp = 0.0018;   % excitation pulse duration
    Prot.Tr = 0.0100;   % free precession after excitation
    Prot.TR = Prot.Tm + Prot.Ts + Prot.Tp + Prot.Tr;   % 0.0250

    Prot.Alpha  = 7;    % read pulse alpha
    Prot.Npulse = 600;  % NOT V1's default of 100 -- modern qMRLab uses 600
    Prot.MTpulse.shape  = 'gausshann';
    Prot.MTpulse.opt.bw = 200;
    Prot.MTpulse.Npulse = 600;
    Prot.Method   = 'SPGR';
    Prot.FileType = 'Protocol';

    FitOpt.names = {'F', 'kr', 'R1f', 'R1r', 'T2f', 'T2r'};
    FitOpt.st = [0.16,   30,      1,    1,    0.03,   1.3e-05];
    FitOpt.lb = [0.0001, 0.0001,  0.05, 0.05, 0.003,  3.0e-06];
    FitOpt.ub = [0.5,    100,     5,    5,    0.5,    5.0e-05];
    FitOpt.fx = [0,      0,       1,    1,    0,      0];

    FitOpt.model     = 'Ramani';
    FitOpt.lineshape = 'SuperLorentzian';
    FitOpt.R1map     = 1;   % use the R1map to constrain R1f (why fx(3) is 1)
    FitOpt.R1reqR1f  = 0;   % do NOT fix R1r = R1f
    FitOpt.FixR1fT2f = 0;
    FitOpt.FixR1fT2fValue = 0.055;
    FitOpt.FileType = 'FitOpt';
end
