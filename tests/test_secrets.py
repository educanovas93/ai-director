import logging
from backend import core


def test_obs_client_child_logger_cannot_emit_password(caplog):
    with caplog.at_level(logging.DEBUG):
        logging.getLogger('obsws_python.baseclient.ObsClient').info("Connecting password='secret-sentinel'")
    assert 'secret-sentinel' not in caplog.text
