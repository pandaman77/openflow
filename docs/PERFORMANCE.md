# Performance

Run the benchmark on your machine:

```powershell
python scripts/benchmark_stt.py --audio tests/fixtures/ru_sample.wav --models tiny,base,small --devices cpu
```

RTF = inference time / audio duration; below 1.0 is faster than realtime.

## Reference: AMD Ryzen 5 6600HS (laptop, CPU int8, beam 1)

| model | infer (8.5 s RU audio) | RTF | quality |
|---|---|---|---|
| small | ~3.4-3.7 s | ~0.42 | good RU/EN, occasional brand-name misses |

(Numbers from the dev machine; GPU numbers TBD — expected 5-15x faster.)

## Tuning knobs

- `stt.model`: tiny/base for weak CPUs, small default, large-v3-turbo on GPU
- `stt.beam_size`: 1 (greedy, default) vs 5 (+accuracy, ~2x slower)
- `stt.compute_type`: int8 CPU / float16 GPU (auto picks these)
- `cleanup.mode`: fast (ms) vs smart (adds seconds on CPU)
- personal dictionary shortens, not lengthens, inference (better priors)
