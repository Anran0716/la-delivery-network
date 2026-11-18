"""Period 2: derive industrial candidates with station locations inside LA County.

The configured county-only scope excludes otherwise plausible Orange/Ventura
stations. Candidate generation must validate its final locations against the
county boundary before any travel-time or optimization step.
"""
