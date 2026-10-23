import numpy as np
import pytest

from face_agent import test_live_match
from face_agent.recognition import cosine_similarity


def test_cosine_similarity_compares_normalized_embeddings():
    left = np.array([1.0, 0.0], dtype=np.float32)
    right = np.array([0.8, 0.6], dtype=np.float32)

    assert cosine_similarity(left, right) == pytest.approx(0.8)


def test_cosine_similarity_rejects_incompatible_embeddings():
    with pytest.raises(ValueError, match="incompatible dimensions"):
        cosine_similarity(np.zeros(2), np.zeros(3))


def test_compare_faces_returns_best_reference_similarity_per_live_frame():
    references = [
        np.array([1.0, 0.0], dtype=np.float32),
        np.array([0.0, 1.0], dtype=np.float32),
    ]
    live = [np.array([0.8, 0.6], dtype=np.float32)]

    assert test_live_match.compare_faces(references, live) == pytest.approx([0.8])


def test_compare_faces_rejects_empty_reference_or_camera_samples():
    with pytest.raises(ValueError, match="No reference face images"):
        test_live_match.compare_faces([], [np.zeros(2)])
    with pytest.raises(ValueError, match="No live camera face samples"):
        test_live_match.compare_faces([np.zeros(2)], [])


def test_decide_match_requires_a_majority_at_or_above_threshold():
    match, accepted, median = test_live_match.decide_match(
        [0.4, 0.2, 0.6, 0.1, 0.5],
        threshold=0.363,
    )

    assert match is True
    assert accepted == 3
    assert median == 0.4


def test_decide_match_rejects_less_than_half_of_live_samples():
    match, accepted, median = test_live_match.decide_match(
        [0.4, 0.3, 0.2, 0.1, 0.3],
        threshold=0.363,
    )

    assert match is False
    assert accepted == 1
    assert median == 0.3


def test_decide_match_rejects_empty_predictions():
    with pytest.raises(ValueError, match="No live camera face samples"):
        test_live_match.decide_match([], threshold=0.363)


def test_find_reference_images_returns_every_supported_image(tmp_path):
    for name in ("Photo-2.jpeg", "anis.jpeg", "notes.txt"):
        (tmp_path / name).touch()

    images = test_live_match.find_reference_images(tmp_path)

    assert [image.name for image in images] == ["anis.jpeg", "Photo-2.jpeg"]


def test_load_reference_faces_uses_all_images(tmp_path, monkeypatch):
    images = [tmp_path / "first.jpeg", tmp_path / "second.jpeg"]
    for image in images:
        image.touch()
    monkeypatch.setattr(
        test_live_match.cv2,
        "imread",
        lambda *_args, **_kwargs: np.zeros((160, 160, 3), dtype=np.uint8),
    )
    embeddings = iter((np.array([1.0, 0.0]), np.array([0.0, 1.0])))
    loaded, paths = test_live_match.load_reference_faces(
        tmp_path,
        embedding_function=lambda _image, *_models: next(embeddings),
        models=(object(), object()),
    )

    assert len(loaded) == 2
    assert paths == images


def test_load_reference_faces_reports_invalid_face_image(tmp_path, monkeypatch):
    image_path = tmp_path / "empty.jpeg"
    image_path.touch()
    monkeypatch.setattr(test_live_match.cv2, "imread", lambda *_args, **_kwargs: np.zeros((1, 1, 3)))

    with pytest.raises(ValueError, match="Invalid reference image empty.jpeg"):
        test_live_match.load_reference_faces(
            tmp_path,
            embedding_function=lambda *_args: (_ for _ in ()).throw(
                ValueError("Expected exactly one face, found 0.")
            ),
            models=(object(), object()),
        )


def test_capture_live_faces_reports_no_face_before_timeout(monkeypatch):
    class Camera:
        def isOpened(self):
            return True

        def read(self):
            return True, np.zeros((160, 160, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(test_live_match.cv2, "VideoCapture", lambda *_args: Camera())
    monkeypatch.setattr(
        test_live_match,
        "face_embedding",
        lambda *_args: (_ for _ in ()).throw(
            ValueError("Expected exactly one face, found 0.")
        ),
    )
    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(test_live_match.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(test_live_match.time, "sleep", lambda *_args: None)

    with pytest.raises(test_live_match.NoLiveFaceError, match="found 0"):
        test_live_match.capture_live_faces(0, (object(), object()), 1, 1.0)


@pytest.mark.parametrize(
    ("similarities", "expected_state", "expected_exit_code"),
    [([0.8], "granted", 0), ([0.1], "face_denied", 1)],
)
def test_led_option_sends_match_result_without_hardware(
    monkeypatch,
    similarities,
    expected_state,
    expected_exit_code,
):
    bridges = []

    class FakeLedSerialBridge:
        def __init__(self, port):
            self.port = port
            self.states = []
            self.closed = False
            bridges.append(self)

        def send(self, state):
            self.states.append(state)

        def close(self):
            self.closed = True

    monkeypatch.setattr(test_live_match, "LedSerialBridge", FakeLedSerialBridge)
    monkeypatch.setattr(test_live_match, "load_face_models", lambda: (object(), object()))
    monkeypatch.setattr(
        test_live_match,
        "load_reference_faces",
        lambda *_args, **_kwargs: ([np.array([1.0])], [test_live_match.Path("reference.jpg")]),
    )
    monkeypatch.setattr(
        test_live_match,
        "capture_live_faces",
        lambda *_args: [np.array([1.0])],
    )
    monkeypatch.setattr(test_live_match, "compare_faces", lambda *_args: similarities)
    monkeypatch.setattr(
        test_live_match.sys,
        "argv",
        ["test_live_match.py", "--led", "--serial-port", "COM_TEST"],
    )

    assert test_live_match.main() == expected_exit_code
    assert len(bridges) == 1
    assert bridges[0].port == "COM_TEST"
    assert bridges[0].states == [expected_state]
    assert bridges[0].closed is True


def test_led_option_reports_face_denied_when_no_live_face(monkeypatch):
    bridges = []

    class FakeLedSerialBridge:
        def __init__(self, port):
            self.port = port
            self.states = []
            self.closed = False
            bridges.append(self)

        def send(self, state):
            self.states.append(state)

        def close(self):
            self.closed = True

    monkeypatch.setattr(test_live_match, "LedSerialBridge", FakeLedSerialBridge)
    monkeypatch.setattr(test_live_match, "load_face_models", lambda: (object(), object()))
    monkeypatch.setattr(
        test_live_match,
        "load_reference_faces",
        lambda *_args, **_kwargs: ([np.array([1.0])], [test_live_match.Path("reference.jpg")]),
    )
    monkeypatch.setattr(
        test_live_match,
        "capture_live_faces",
        lambda *_args: (_ for _ in ()).throw(test_live_match.NoLiveFaceError("no face")),
    )
    monkeypatch.setattr(
        test_live_match.sys,
        "argv",
        ["test_live_match.py", "--led", "--serial-port", "COM_TEST"],
    )

    assert test_live_match.main() == 1
    assert len(bridges) == 1
    assert bridges[0].states == ["face_denied"]
    assert bridges[0].closed is True
