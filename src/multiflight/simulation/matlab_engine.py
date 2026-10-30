import logging

from ..settings import MODEL_FILE, SIMULINK_DIR

try:
    import matlab.engine as matlab_engine
except ImportError:  # The API and unit tests can start without MATLAB installed.
    matlab_engine = None

logger = logging.getLogger(__name__)

_engine = None


def get_engine():

    global _engine

    if _engine is not None:
        return _engine

    if matlab_engine is None:
        raise RuntimeError(
            "MATLAB Engine for Python is unavailable. Install it from the local "
            "MATLAB R2022a installation, start MATLAB, and run "
            "matlab.engine.shareEngine."
        )

    logger.info("Connecting MATLAB...")

    names = matlab_engine.find_matlab()

    if not names:
        raise RuntimeError(
            "请先在MATLAB执行 matlab.engine.shareEngine"
        )

    _engine = matlab_engine.connect_matlab(names[0])

    _engine.cd(str(SIMULINK_DIR), nargout=0)

    _engine.load_system(str(MODEL_FILE), nargout=0)

    logger.info("MATLAB Ready.")

    return _engine
