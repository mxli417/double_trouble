from math import pow


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + pow(10.0, (rating_b - rating_a) / 400.0))


def update_pair(rating_winner: float, rating_loser: float, k_factor: float = 24.0) -> tuple[float, float]:
    winner_expected = expected_score(rating_winner, rating_loser)
    loser_expected = expected_score(rating_loser, rating_winner)
    return (
        rating_winner + k_factor * (1.0 - winner_expected),
        rating_loser + k_factor * (0.0 - loser_expected),
    )
