import sys
from unittest.mock import patch, MagicMock
from src.main import main

@patch("src.main.check_api_key_or_toast_and_exit")
@patch("src.main.QApplication")
@patch("src.main.TranscriberService")
@patch("src.main.AudioStreamHandler")
@patch("src.main.TrayIconController")
def test_main_initialization_pipeline(
    mock_tray_controller_class,
    mock_audio_handler_class,
    mock_transcriber_class,
    mock_qapp_class,
    mock_check_key
):
    # Setup mocks
    mock_check_key.return_value = "mocked-api-key"
    mock_app_instance = MagicMock()
    mock_qapp_class.return_value = mock_app_instance
    
    mock_audio_handler = MagicMock()
    mock_audio_handler_class.return_value = mock_audio_handler
    
    mock_tray_controller = MagicMock()
    mock_tray_controller_class.return_value = mock_tray_controller

    # Mock app.exec() to prevent blocking the test run
    mock_qapp_class.instance.return_value = mock_app_instance
    sys.exit = MagicMock()

    # Act: Trigger main boot sequence
    main()

    # Assert: 1. Key is checked first
    mock_check_key.assert_called_once()

    # Assert: 2. QApplication is configured to remain running when child windows close
    mock_qapp_class.assert_called_once()
    mock_app_instance.setQuitOnLastWindowClosed.assert_called_once_with(False)

    # Assert: 3. Core background services are instantiated
    mock_transcriber_class.assert_called_once_with(
        api_key="mocked-api-key",
        config_dict={
            "GEMINI_API_KEY": "mocked-api-key",
            "GEMINI_MODEL": "gemini-3.5-transcribe",
            "STT_PROVIDER": "gemini",
            "GCP_PROJECT_ID": "",
            "GCP_REGION": "us",
            "GCP_SERVICE_ACCOUNT_KEY_PATH": "",
            "GCP_LANGUAGES": ["zh-CN", "en-US"],
            "GITHUB_REPO": "shuaiyuancn/buddy",
            "AUTO_UPDATE": True,
            "UPDATE_CHECK_INTERVAL_HOURS": 1
        }
    )
    mock_audio_handler_class.assert_called_once_with(target_sr=16000, window_duration_sec=60)
    mock_tray_controller_class.assert_called_once_with(
        audio_handler=mock_audio_handler,
        transcriber_service=mock_transcriber_class.return_value
    )

    # Assert: 4. Audio recorder thread and tray icons are booted and visible
    mock_audio_handler.start.assert_called_once()
    mock_tray_controller.show.assert_called_once()
    
    # Assert: 5. Qt Event Loop starts running
    mock_app_instance.exec.assert_called_once()
