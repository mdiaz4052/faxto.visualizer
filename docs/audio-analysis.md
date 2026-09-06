# Audio analysis

The Phase 0 analyzer reads uncompressed PCM WAV, downmixes to mono for analysis, and preserves original channel/sample-rate metadata. It calculates overlapping-window RMS, low/mid/high FFT band power, spectral centroid and positive spectral flux. Curves are sampled at a documented hop interval.

Curve amplitudes other than centroid are robustly normalized against their own 95th percentile. Onsets are local spectral-flux peaks over a median-deviation threshold. Tempo is emitted only when enough plausible onset intervals exist; its intentionally low confidence communicates that it is an estimate. Tonal center and structural sections remain empty rather than fabricating certainty.

The source SHA-256 makes an analysis traceable to its WAV. The JSON Schema is the normative interchange contract; the dependency-light Python validator supplies clear runtime failures.

