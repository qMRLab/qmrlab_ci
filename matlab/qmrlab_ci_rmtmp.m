function qmrlab_ci_rmtmp(d)
%QMRLAB_CI_RMTMP Remove a temporary directory if one was created.
    if ~isempty(d) && exist(d, 'dir')
        rmdir(d, 's');
    end
end
