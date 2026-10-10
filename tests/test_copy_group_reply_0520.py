"""Returned success values cannot replace a read-back of favorite A."""
import unittest
from unittest.mock import patch
import tv_write
from test_copy_migration_0517 import CopySim, SAT, A, A26
from lg_fixtures import assert_raises_message, message_keys

SOURCE={'db_id':A, 'name':'ARD-alpha HD', 'number':'125',
        'groups':{g:g=='A' for g in tv_write.GROUPS}}

class FalseReplyButApplied(CopySim):
    def luna(self, client, method, payload, service=None):
        result=super().luna(client,method,payload,service=service)
        if method == 'setChannelFavoriteGroup':
            return {'returnValue':False}
        return result

class FalseReleaseButApplied(CopySim):
    def luna(self, client, method, payload, service=None):
        result=super().luna(client,method,payload,service=service)
        if method == 'releaseChannelFavoriteGroup':
            return {'returnValue':False}
        return result

class FailureTests(unittest.TestCase):
    def start(self, cls=CopySim):
        return cls([(A,'ARD-alpha HD',125,['A']),(A26,'ARD-alpha HD',26,[])])

    def test_false_group_response_but_effect_verified_succeeds(self):
        sim=self.start(FalseReplyButApplied)
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write._migrate_copy_favorites(None,SOURCE,A26,A)
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])

    def test_false_reply_no_effect_keeps_old_favorite_and_names_both_ids(self):
        sim=self.start()
        sim.fail='setChannelFavoriteGroup'
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            with self.assertRaises(ValueError) as cm:
                tv_write._migrate_copy_favorites(None,SOURCE,A26,A)
        err=str(cm.exception)
        self.assertIn('ARD-alpha HD',err)
        self.assertIn(A,err)
        self.assertIn(A26,err)
        self.assertIn("'returnValue': False",err)
        self.assertIn('error.copy.add_a_unconfirmed',message_keys(cm.exception))
        self.assertIn("current []",err)
        self.assertEqual([name for name,_ in sim.calls],['setChannelFavoriteGroup'])
        self.assertEqual(sim._idx(A)['favoriteGroup'],['A'])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],[])

    def test_false_release_but_effect_verified_succeeds(self):
        sim=self.start(FalseReleaseButApplied)
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write._migrate_copy_favorites(None,SOURCE,A26,A)
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])

    def test_false_release_no_effect_reports_partial_state(self):
        sim=self.start()
        sim.fail='releaseChannelFavoriteGroup'
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            with assert_raises_message(self, 'error.copy.remove_a_unconfirmed'):
                tv_write._migrate_copy_favorites(None,SOURCE,A26,A)
        self.assertEqual(sim._idx(A)['favoriteGroup'],['A'])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        self.assertEqual([name for name,_ in sim.calls],
                         ['setChannelFavoriteGroup','releaseChannelFavoriteGroup'])

if __name__=='__main__': unittest.main()
