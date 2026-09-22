# Cache experiment

The cache reduces repeated database reads by storing query results in memory for 60 seconds and serving matching requests from that memory.

In our local test, 100 identical requests produced one database read with the cache enabled and 100 reads with it disabled.

This test covers repeated identical requests only; it does not measure production latency or behavior when data changes.
