from unittest.mock import MagicMock, patch

from src.audio.stream_handler import AudioStreamHandler


def _device(device_id, name=None):
    d = MagicMock(id=device_id)
    d.name = name or device_id
    return d


def test_follows_windows_default_when_nothing_selected():
    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False})
    fake_sc = MagicMock()
    fake_sc.default_microphone.return_value = _device("laptop-mic")
    fake_sc.all_microphones.return_value = [_device("laptop-mic"), _device("usb-mic")]
    with patch("src.audio.stream_handler.sc", fake_sc):
        assert handler._selected_microphone().id == "laptop-mic"


def test_uses_selected_device_from_config():
    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False, "MICROPHONE_DEVICE_ID": "usb-mic",
                                              "SPEAKER_DEVICE_ID": "headphones"})
    fake_sc = MagicMock()
    fake_sc.default_microphone.return_value = _device("laptop-mic")
    fake_sc.all_microphones.return_value = [_device("laptop-mic"), _device("usb-mic")]
    fake_sc.default_speaker.return_value = _device("speakers")
    fake_sc.all_speakers.return_value = [_device("speakers"), _device("headphones")]
    with patch("src.audio.stream_handler.sc", fake_sc):
        assert handler._selected_microphone().id == "usb-mic"
        assert handler._selected_speaker().id == "headphones"


def test_unplugged_selection_falls_back_to_default_and_returns_when_reconnected():
    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False, "MICROPHONE_DEVICE_ID": "usb-mic"})
    fake_sc = MagicMock()
    fake_sc.default_microphone.return_value = _device("laptop-mic")
    fake_sc.all_microphones.return_value = [_device("laptop-mic")]
    with patch("src.audio.stream_handler.sc", fake_sc):
        assert handler._selected_microphone().id == "laptop-mic"
        # The capture thread's periodic check sees the selected device again and reopens on it
        fake_sc.all_microphones.return_value = [_device("laptop-mic"), _device("usb-mic")]
        assert handler._default_device_changed(handler._selected_microphone, "laptop-mic") is True
        assert handler._selected_microphone().id == "usb-mic"


def test_tray_device_menu_lists_devices_and_saves_choice():
    from src.ui.tray_icon import TrayIconController

    audio = MagicMock(preferred_mic_id="", preferred_speaker_id="")
    controller = TrayIconController(audio_handler=audio, transcriber_service=MagicMock(), updater=MagicMock(), config_dict={})
    with patch("soundcard.all_microphones", return_value=[_device("laptop-mic", "Microphone Array"), _device("usb-mic", "Yeti")]), \
         patch("soundcard.default_microphone", return_value=_device("laptop-mic", "Microphone Array")), \
         patch("src.ui.tray_icon.save_config_key", return_value=True) as save:
        controller._populate_device_menu("microphone")
        labels = [a.text() for a in controller.mic_menu.actions() if not a.isSeparator()]
        assert labels == ["System default (Microphone Array)", "Microphone Array", "Yeti"]
        assert controller.mic_menu.actions()[0].isChecked()

        next(a for a in controller.mic_menu.actions() if a.text() == "Yeti").trigger()

    assert audio.preferred_mic_id == "usb-mic"
    save.assert_called_once_with("MICROPHONE_DEVICE_ID", "usb-mic")
