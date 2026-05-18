from src.sparkline import sparkline


class TestSparkline:
    def test_empty_returns_empty(self):
        assert sparkline([]) == ""

    def test_single_value_returns_empty(self):
        assert sparkline([0.5]) == ""

    def test_two_values(self):
        result = sparkline([0.0, 1.0])
        assert len(result) == 2
        assert result[0] == "▁"
        assert result[-1] == "█"

    def test_constant_values(self):
        result = sparkline([0.5, 0.5, 0.5])
        assert result == "▅▅▅"

    def test_ascending(self):
        result = sparkline([0.0, 0.25, 0.5, 0.75, 1.0])
        assert len(result) == 5
        # Should be ascending bars
        assert result[0] < result[-1]

    def test_descending(self):
        result = sparkline([1.0, 0.5, 0.0])
        assert result[0] > result[-1]

    def test_real_scores(self):
        result = sparkline([0.42, 0.45, 0.51, 0.48, 0.55])
        assert len(result) == 5
        # All characters should be valid bar chars
        for char in result:
            assert char in "▁▂▃▄▅▆▇█"
