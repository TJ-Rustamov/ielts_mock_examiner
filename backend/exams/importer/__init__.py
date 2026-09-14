"""PDF -> structured IELTS test importer.

Stage order (see the plan): ingest -> pages -> preprocess -> cleanup -> segment
-> classify -> parse -> answer keys -> figures -> draft -> publish.

Every module here is import-time only. Nothing in this package is touched while
a candidate is sitting a test.
"""
