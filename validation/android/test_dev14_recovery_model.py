#!/usr/bin/env python3
import unittest
class Gen:
 def __init__(s,target=None): s.target=target;s.first=None;s.terminal=None;s.state='UNFILTERED_RECOVERY';s.start=0;s.probe=None
 def cb(s,t,p):
  if s.terminal or s.state!='UNFILTERED_RECOVERY' or (s.target and p!=s.target): return False
  if s.first is None: s.first=(t,p); return True
  return False
 def success(s,t,p):
  if s.terminal or not s.first or (s.target and (p!=s.target or s.first[1]!=s.target)): return False
  s.terminal='SUCCESS';s.state='FILTERED_RECOVERY_PROBE';s.probe=t;return True
 def fail(s,t):
  if s.terminal:return False
  s.terminal='FAILURE';s.state='FILTERED_RECOVERY_PROBE';s.probe=t;return True
 def tick(s,t):
  if s.state=='FILTERED_RECOVERY_PROBE' and t-s.probe>=14500:s.state='FILTERED_PRIMARY'
class T(unittest.TestCase):
 def test_target(s): g=Gen('A');s.assertFalse(g.cb(1,'B'));s.assertTrue(g.cb(2,'A'));s.assertTrue(g.success(3,'A'))
 def test_success_requires_first(s): g=Gen('A');s.assertFalse(g.success(2,'A'))
 def test_terminal_exactly_once(s): g=Gen();g.cb(1,'A');s.assertTrue(g.success(2,'A'));s.assertFalse(g.success(3,'A'));s.assertFalse(g.fail(4));s.assertFalse(g.cb(5,'A'))
 def test_failure_terminal(s): g=Gen();s.assertTrue(g.fail(10000));s.assertEqual(g.state,'FILTERED_RECOVERY_PROBE')
 def test_probe_jitter(s):
  for jitter in range(0,1001,50):
   g=Gen();g.cb(1,'A');g.success(2,'A');g.tick(2+14500+jitter);s.assertEqual(g.state,'FILTERED_PRIMARY')
 def test_start_provenance_survives_probe(s): g=Gen();g.cb(1,'A');g.success(2,'A');s.assertEqual(g.start,0)
unittest.main()
