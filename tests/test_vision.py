import cv2
import numpy as np
from catwatch.vision import COLOR_BINS, descriptor, identify, identify_night, in_zone


def color(bgr):
    return np.full((40, 40, 3), bgr, dtype=np.uint8)


def test_mask_excludes_background_and_profiles_separate_coats():
    mask = np.ones((40, 40), dtype=np.uint8)
    a = descriptor(color((20,20,20)), mask)
    b = descriptor(color((230,230,230)), mask)
    profiles = {"冲冲":[a.tolist()]*3, "茉莉":[b.tolist()]*3}
    assert identify(a, profiles)[0] == "冲冲"
    assert identify(b, profiles)[0] == "茉莉"
    assert identify(a, {"冲冲":[a.tolist()]})[0] == "unknown"
    assert identify(a, {"冲冲":[a.tolist()], "茉莉":[a.tolist()]})[0] == "unknown"
    mask[:, :20] = 0
    image = color((20,20,20))
    image[:, :20] = (230,230,230)
    assert np.allclose(descriptor(image, mask), a)


def test_zone_fraction_and_tiny_mask():
    mask = np.zeros((100,100), np.uint8)
    mask[30:70,30:70] = 1
    assert in_zone(mask, [.3,.3,.7,.7], .5)
    assert not in_zone(mask, [0,0,.1,.1], .1)
    assert descriptor(color((0,0,0)), np.zeros((40,40), np.uint8)) is None


def test_pattern_vetoes_wrong_color_match_when_light_drops():
    mask = np.ones((40, 40), dtype=np.uint8)
    bright = color((200, 200, 200))
    bright[:, :20] = 20
    dim = (bright * .4).astype(np.uint8)
    different_pattern = color((80, 80, 80))
    different_pattern[:20, :] = 8
    profiles = {"白猫": [descriptor(bright, mask)], "冲冲": [descriptor(different_pattern, mask)]}
    legacy = {name: [samples[0][:COLOR_BINS]] for name, samples in profiles.items()}
    query = descriptor(dim, mask)
    assert identify(query[:COLOR_BINS], legacy)[0] == "冲冲"
    assert identify(query, profiles)[0] == "unknown"


def test_night_requires_both_color_and_pattern_to_agree():
    mask = np.ones((40, 40), dtype=np.uint8)
    first = color((50, 50, 50))
    first[:, :20] = 10
    second = color((110, 110, 110))
    second[:20, :] = 90
    chong, white = descriptor(first, mask), descriptor(second, mask)
    profiles = {"冲冲": [chong], "白猫": [white]}
    conflicting = np.concatenate((chong[:COLOR_BINS], white[COLOR_BINS:]))

    assert identify_night(chong, profiles) == "冲冲"
    assert identify_night(white, profiles) == "白猫"
    assert identify_night(conflicting, profiles) == "unknown"
    assert identify_night(chong[:COLOR_BINS], profiles) == "unknown"
