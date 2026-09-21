"""Checka ut och checka in en databasplan (kräver QGIS).

Ingen riktig databas används: en GeoPackage står i för databasens tabeller (lagren läses därifrån) och en låtsasanslutning
tar emot och tolkar den SQL som pluginet skickar (lås, släpp lås, incheckning). Att incheckningens SQL fungerar mot en
riktig PostgreSQL med PostGIS är därför inte provat här."""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import Qgis, QgsDataSourceUri, QgsProject, QgsVectorLayer
    from qgis.PyQt.QtCore import QDate, QDateTime
    from rita_detaljplan.core import checkout as co
    from rita_detaljplan.core import geopackage, model, storage
    from rita_detaljplan.core.project import DB_SCOPE, find_layer, load_plan
    from rita_detaljplan.gui.checkout_actions import CANCEL, CHECK_IN, DISCARD, CheckoutActions
    from test_export import ExportCase


class FakePg:
    """Låtsasdatabas för en plan: metadata med lås, och en logg över den SQL som skickats."""

    def __init__(self, meta):
        self.meta = dict(meta)
        self.sql = []
        self.fail_on = None
        self.checkins = []

    def uri(self):
        return "dbname='planer' host=localhost port=5432 user='eric' sslmode=disable"

    def executeSql(self, sql):
        self.sql.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("syntaxfel nära " + self.fail_on)
        if sql.startswith('SELECT "key", "value"'):
            return [[k, v] for k, v in self.meta.items()]
        if sql.startswith("DO $dp$ BEGIN LOCK TABLE"):
            match = re.search(r"VALUES \('checkout', '(.*)'\); END IF", sql)
            if "checkout" not in self.meta:
                self.meta["checkout"] = match.group(1).replace("''", "'")
            return []
        if sql.startswith("DO $dp"):  # incheckning
            token = re.search(r'"token": "([0-9a-f]+)"', sql).group(1)
            held = json.loads(self.meta["checkout"])["token"] if "checkout" in self.meta else None
            if held != token:
                raise RuntimeError("Låset på planen tillhör inte längre dig. Planen har inte checkats in.")
            self.checkins.append(sql)
            del self.meta["checkout"]
            return []
        if sql.startswith("DELETE FROM") and "'checkout'" in sql:
            token = re.search(r'"token": "([0-9a-f]+)"', sql)
            if "checkout" in self.meta and (token is None or json.loads(self.meta["checkout"])["token"] == token.group(1)):
                del self.meta["checkout"]
            return []
        return []


def other_lock():
    return co.Lock("f" * 32, "anna", "ANNAS-DATOR", "2026-09-20T09:00:00")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CheckoutCase(ExportCase):
    """Den färdiga planen i ExportCase, förklarad som en databasplan: GeoPackagen är 'databasen'."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.controller.stop_editing(save=True), [])
        self.project = QgsProject.instance()
        self.conn = FakePg(geopackage.read_meta(self.gpkg))
        self.plan = storage.PostgisStorage("db", "dp_test", self.conn)
        self.copies = self.dir / "copies"
        gpkg = Path(self.gpkg)

        def open_layer(storage_self, uri, alias):
            return QgsVectorLayer(uri, alias, "ogr")

        patches = [
            mock.patch.object(co, "DB_PROVIDER", "ogr"),
            mock.patch.object(co, "_is_db_layer", lambda layer: Path(layer.source().split("|")[0]) == gpkg),
            mock.patch.object(storage.PostgisStorage, "layer_uri",
                              lambda s, d, epsg=None: f"{gpkg.as_posix()}|layername={d.name}"),
            mock.patch.object(storage.PostgisStorage, "_open", open_layer),
            mock.patch.object(storage, "postgis_connections", lambda: {"db": self.conn}),
            mock.patch.object(co, "checkouts_dir", lambda: self.copies),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.project.writeEntry(DB_SCOPE, "connection", "db")
        self.project.writeEntry(DB_SCOPE, "schema", "dp_test")
        for layer in self.layers.values():
            layer.setReadOnly(True)

    def count(self, table, layer=None):
        return (layer or self.layers[table]).featureCount()

    def counts(self):
        return {d.name: find_layer(self.project, d.name).featureCount() for d in model.LAYERS}


class LockTests(CheckoutCase):
    def test_a_free_plan_can_be_locked_and_the_lock_says_who_and_since_when(self):
        lock = co.acquire_lock(self.plan)
        held = co.read_lock(self.plan)
        self.assertEqual(held, lock)
        self.assertTrue(lock.user)
        self.assertRegex(lock.since, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        self.assertIn("sedan", lock.describe())

    def test_a_locked_plan_cannot_be_locked_again_and_the_error_names_the_owner(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        with self.assertRaises(co.LockedError) as caught:
            co.acquire_lock(self.plan)
        self.assertEqual(caught.exception.lock, other_lock())
        self.assertIn("anna på ANNAS-DATOR", str(caught.exception))
        self.assertEqual(co.read_lock(self.plan), other_lock(), "den andras lås är orört")

    def test_the_lock_is_taken_while_the_meta_table_is_locked(self):
        co.acquire_lock(self.plan)
        sql = next(s for s in self.conn.sql if s.startswith("DO $dp$ BEGIN LOCK TABLE"))
        self.assertIn('LOCK TABLE "dp_test"."dp_meta" IN EXCLUSIVE MODE', sql)
        self.assertIn("IF NOT EXISTS", sql)

    def test_only_the_owner_releases_the_lock_but_anyone_can_break_it(self):
        lock = co.acquire_lock(self.plan)
        co.release_lock(self.plan, "0" * 32)
        self.assertEqual(co.read_lock(self.plan), lock)
        co.release_lock(self.plan, lock.token)
        self.assertIsNone(co.read_lock(self.plan))
        self.conn.meta["checkout"] = other_lock().to_json()
        co.break_lock(self.plan)
        self.assertIsNone(co.read_lock(self.plan))

    def test_a_broken_lock_value_counts_as_no_lock_owner_but_still_blocks(self):
        self.conn.meta["checkout"] = "skräp"
        self.assertIsNone(co.read_lock(self.plan))
        self.assertEqual(co.Lock.from_json('{"token": "a"}'), co.Lock("a", "", "", ""))
        self.assertIsNone(co.Lock.from_json("{}"))

    def test_database_errors_become_postgis_errors(self):
        self.conn.fail_on = "LOCK TABLE"
        with self.assertRaises(storage.PostgisError):
            co.acquire_lock(self.plan)


class StateTests(CheckoutCase):
    def test_a_database_plan_is_read_only_and_reports_its_state(self):
        self.assertEqual(co.state(self.project), co.DATABASE)
        self.assertEqual(co.db_source(self.project), self.plan)

    def test_a_plan_in_a_file_is_not_a_database_plan(self):
        with mock.patch.object(co, "_is_db_layer", lambda layer: False):
            self.assertEqual(co.state(self.project), co.FILE)

    def test_projects_from_older_versions_are_made_read_only(self):
        for layer in self.layers.values():
            layer.setReadOnly(False)
        co.enforce_read_only(self.project)
        self.assertTrue(all(layer.readOnly() for layer in self.layers.values()))

    def test_read_only_is_not_forced_on_a_plan_in_a_file(self):
        for layer in self.layers.values():
            layer.setReadOnly(False)
        with mock.patch.object(co, "_is_db_layer", lambda layer: False):
            co.enforce_read_only(self.project)
        self.assertFalse(any(layer.readOnly() for layer in self.layers.values()))

    def test_the_connection_is_found_by_the_address_of_the_layers_when_the_project_does_not_say(self):
        self.project.writeEntry(DB_SCOPE, "connection", "")
        self.project.writeEntry(DB_SCOPE, "schema", "")
        layer = self.layers["detaljplan"]
        uri = QgsDataSourceUri()
        uri.setConnection("localhost", "5432", "planer", "eric", "")
        uri.setDataSource("dp_test", "detaljplan", "geom")
        with mock.patch.object(layer, "source", return_value=uri.uri(False)),                 mock.patch.object(co, "_is_db_layer", lambda layer: True):
            self.assertEqual(co.db_source(self.project), storage.PostgisStorage("db", "dp_test"))

    def test_load_plan_marks_a_postgis_plan_read_only_and_remembers_where_it_is(self):
        project = QgsProject()
        layers = load_plan(storage.PostgisStorage("db", "dp_test", self.conn), project)
        self.assertTrue(all(layer.readOnly() for layer in layers.values()))
        self.assertEqual(project.readEntry(DB_SCOPE, "connection")[0], "db")
        self.assertEqual(project.readEntry(DB_SCOPE, "schema")[0], "dp_test")

    def test_load_plan_leaves_a_file_plan_writable(self):
        project = QgsProject()
        layers = load_plan(self.gpkg, project)
        self.assertFalse(any(layer.readOnly() for layer in layers.values()))
        self.assertEqual(project.readEntry(DB_SCOPE, "connection")[0], "")


class CheckOutTests(CheckoutCase):
    def test_checking_out_locks_the_plan_and_copies_every_table(self):
        before = self.counts()
        self.assertGreater(before["anvandning_yta"], 0)
        path = co.check_out(self.project, self.copies)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent, self.copies)
        self.assertEqual(co.state(self.project), co.LOCAL)
        self.assertIsNotNone(co.read_lock(self.plan))
        self.assertEqual(self.counts(), before)
        for layer_def in model.LAYERS:
            self.assertIn(path.as_posix(), find_layer(self.project, layer_def.name).source().replace("\\", "/"))

    def test_the_copy_is_editable_while_the_database_layers_were_read_only(self):
        co.check_out(self.project, self.copies)
        self.assertFalse(any(find_layer(self.project, d.name).readOnly() for d in model.LAYERS))

    def test_the_copy_has_the_same_rows_ids_and_geometries(self):
        original = {d.name: sorted((f["fid"], f.geometry().asWkt(3) if f.geometry() else "") for f in
                                   self.layers[d.name].getFeatures()) for d in model.LAYERS}
        co.check_out(self.project, self.copies)
        copy = {d.name: sorted((f["fid"], f.geometry().asWkt(3) if f.geometry() else "") for f in
                               find_layer(self.project, d.name).getFeatures()) for d in model.LAYERS}
        self.assertEqual(copy, original)

    def test_the_layers_keep_their_ids_style_and_configuration(self):
        ids = {d.name: find_layer(self.project, d.name).id() for d in model.LAYERS}
        renderer = self.layers["anvandning_yta"].renderer().referenceScale()
        relations = len(self.project.relationManager().relations())
        co.check_out(self.project, self.copies)
        self.assertEqual({d.name: find_layer(self.project, d.name).id() for d in model.LAYERS}, ids)
        layer = find_layer(self.project, "anvandning_yta")
        self.assertEqual(layer.renderer().referenceScale(), renderer)
        self.assertEqual(layer.customProperty("detaljplan_ngp/table"), "anvandning_yta")
        self.assertEqual(len(self.project.relationManager().relations()), relations)
        self.assertEqual(layer.defaultValueDefinition(layer.fields().indexOf("objektidentitet")).expression(),
                         model.UUID_EXPR)

    def test_the_copy_remembers_who_it_belongs_to(self):
        path = co.check_out(self.project, self.copies)
        lock = co.read_lock(self.plan)
        meta = geopackage.read_meta(path)
        self.assertEqual((meta["checkout_token"], meta["checkout_connection"], meta["checkout_schema"]),
                         (lock.token, "db", "dp_test"))
        self.assertEqual(meta["kommun"], geopackage.read_meta(self.gpkg)["kommun"])
        self.assertNotIn("checkout", meta, "själva låset följer inte med")
        self.assertEqual(meta["schema_version"], str(model.SCHEMA_VERSION))

    def test_the_project_remembers_the_checkout(self):
        path = co.check_out(self.project, self.copies)
        self.assertEqual(co.local_path(self.project), path)
        self.assertEqual(self.project.readEntry(DB_SCOPE, "checkout_token")[0], co.read_lock(self.plan).token)

    def test_a_plan_locked_by_someone_else_is_not_copied(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        with self.assertRaises(co.LockedError):
            co.check_out(self.project, self.copies)
        self.assertEqual(co.state(self.project), co.DATABASE)
        self.assertEqual(list(self.copies.glob("*")) if self.copies.exists() else [], [])
        self.assertEqual(co.read_lock(self.plan), other_lock())

    def test_a_failing_copy_releases_the_lock_and_leaves_the_project_as_it_was(self):
        with mock.patch.object(co, "download", side_effect=co.CheckoutError("nätverket föll")):
            with self.assertRaisesRegex(co.CheckoutError, "Kunde inte checka ut planen: nätverket föll"):
                co.check_out(self.project, self.copies)
        self.assertIsNone(co.read_lock(self.plan))
        self.assertEqual(co.state(self.project), co.DATABASE)
        self.assertTrue(all(layer.readOnly() for layer in self.layers.values()))
        self.assertEqual(self.counts(), {d.name: self.layers[d.name].featureCount() for d in model.LAYERS})

    def test_a_half_written_copy_is_removed_when_the_copy_fails(self):
        def broken(plan, path, lock):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"halv")
            raise co.CheckoutError("disken är full")

        with mock.patch.object(co, "download", broken):
            with self.assertRaises(co.CheckoutError):
                co.check_out(self.project, self.copies)
        self.assertEqual(list(self.copies.glob("*")), [])

    def test_a_plan_in_a_file_and_an_edit_session_in_progress_refuse_checkout(self):
        with mock.patch.object(co, "_is_db_layer", lambda layer: False):
            with self.assertRaisesRegex(co.CheckoutError, "inte i en databas"):
                co.check_out(self.project, self.copies)
        self.layers["anvandning_yta"].setReadOnly(False)
        self.layers["anvandning_yta"].startEditing()
        with self.assertRaisesRegex(co.CheckoutError, "Avsluta redigeringen"):
            co.check_out(self.project, self.copies)
        self.assertIsNone(co.read_lock(self.plan), "inget lås togs")

    def test_an_unknown_connection_is_reported(self):
        self.project.writeEntry(DB_SCOPE, "connection", "")
        self.project.writeEntry(DB_SCOPE, "schema", "")
        with mock.patch.object(co, "db_source", return_value=None):
            with self.assertRaisesRegex(co.CheckoutError, "databasanslutningen"):
                co.check_out(self.project, self.copies)


class CheckInTests(CheckoutCase):
    def out(self):
        return co.check_out(self.project, self.copies)

    def edit_copy(self):
        """Lägger en ny användningsyta och tar bort en egenskapslinje i kopian."""
        self.controller.attach()
        self.controller.start_editing()
        layer = find_layer(self.project, "anvandning_yta")
        feature = self.add_in(layer, "MultiPolygon(((200 0, 210 0, 210 10, 200 10, 200 0)))")
        line_layer = find_layer(self.project, "egenskap_linje")
        line_layer.selectAll()
        line_layer.deleteSelectedFeatures()
        self.assertEqual(self.controller.stop_editing(save=True), [])
        return feature

    def add_in(self, layer, wkt):
        from qgis.core import QgsFeature, QgsGeometry
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        self.assertTrue(layer.addFeature(feature))
        pump()
        return feature

    def test_checking_in_writes_one_transaction_with_every_table_and_releases_the_lock(self):
        path = self.out()
        edited = self.edit_copy()
        expected = self.counts()
        done_path, removed = co.check_in(self.project)
        self.assertEqual((done_path, removed), (path, True))
        (sql,) = self.conn.checkins
        self.assertTrue(sql.startswith("DO $dp$ BEGIN IF NOT EXISTS"))
        self.assertTrue(sql.endswith("END $dp$"))
        for layer_def in model.LAYERS:
            table = f'"dp_test"."{layer_def.name}"'
            self.assertEqual(sql.count(f"DELETE FROM {table};"), 1, layer_def.name)
            rows = sum(len(re.findall(r"^\(|\), \(", chunk)) for chunk in re.findall(
                rf"INSERT INTO {re.escape(table)} \(.*?\) VALUES (.*?);", sql, re.S))
            self.assertEqual(rows, expected[layer_def.name], layer_def.name)
        self.assertIn("ST_Multi(ST_GeomFromText('MultiPolygon", sql)
        self.assertIn("PERFORM setval(", sql)
        self.assertIsNone(co.read_lock(self.plan))

    def test_the_transaction_checks_the_lock_first_and_releases_it_last(self):
        self.out()
        co.check_in(self.project)
        (sql,) = self.conn.checkins
        token = re.search(r'"token": "([0-9a-f]+)"', sql).group(1)
        self.assertNotIn("::json", sql)
        self.assertTrue(sql.index("RAISE EXCEPTION") < sql.index("DELETE FROM \"dp_test\".\"detaljplan\""))
        self.assertTrue(sql.rindex('DELETE FROM "dp_test"."dp_meta"') > sql.rindex("PERFORM setval("))
        self.assertEqual(len(token), 32)

    def test_afterwards_the_layers_point_at_the_database_again_and_the_copy_is_gone(self):
        path = self.out()
        co.check_in(self.project)
        self.assertEqual(co.state(self.project), co.DATABASE)
        self.assertFalse(path.exists())
        self.assertTrue(all(find_layer(self.project, d.name).readOnly() for d in model.LAYERS))
        self.assertEqual(co.local_path(self.project), None)
        self.assertEqual(list(self.copies.glob("*")), [])

    def test_a_failing_checkin_changes_nothing_and_keeps_the_copy_and_the_lock(self):
        path = self.out()
        self.conn.fail_on = "DO $dp$ BEGIN IF NOT EXISTS"
        with self.assertRaisesRegex(co.CheckoutError, "Kunde inte checka in planen"):
            co.check_in(self.project)
        self.assertTrue(path.exists())
        self.assertEqual(co.state(self.project), co.LOCAL)
        self.assertIsNotNone(co.read_lock(self.plan))
        self.assertFalse(any(find_layer(self.project, d.name).readOnly() for d in model.LAYERS))

    def test_a_broken_lock_stops_the_checkin(self):
        path = self.out()
        co.break_lock(self.plan)
        with self.assertRaisesRegex(co.CheckoutError, "tillhör inte längre dig"):
            co.check_in(self.project)
        self.assertTrue(path.exists(), "ändringarna finns kvar i den lokala kopian")
        self.assertEqual(self.conn.checkins, [])

    def test_a_plan_that_is_not_checked_out_or_is_being_edited_is_refused(self):
        with self.assertRaisesRegex(co.CheckoutError, "inte utcheckad"):
            co.check_in(self.project)
        self.out()
        find_layer(self.project, "anvandning_yta").startEditing()
        with self.assertRaisesRegex(co.CheckoutError, "Avsluta redigeringen"):
            co.check_in(self.project)
        self.assertEqual(self.conn.checkins, [])

    def test_discarding_releases_the_lock_removes_the_copy_and_writes_nothing(self):
        path = self.out()
        self.edit_copy()
        done, removed = co.discard(self.project)
        self.assertEqual((done, removed), (path, True))
        self.assertFalse(path.exists())
        self.assertIsNone(co.read_lock(self.plan))
        self.assertEqual(self.conn.checkins, [])
        self.assertEqual(co.state(self.project), co.DATABASE)

    def test_discarding_needs_a_checkout_and_no_edit_session(self):
        with self.assertRaisesRegex(co.CheckoutError, "inte utcheckad"):
            co.discard(self.project)
        self.out()
        find_layer(self.project, "anvandning_yta").startEditing()
        with self.assertRaisesRegex(co.CheckoutError, "Avsluta redigeringen"):
            co.discard(self.project)

    def test_a_copy_that_cannot_be_deleted_is_reported_not_fatal(self):
        self.out()
        with mock.patch.object(co, "_remove", return_value=False):
            path, removed = co.check_in(self.project)
        self.assertFalse(removed)
        self.assertEqual(co.state(self.project), co.DATABASE)


class ResumeTests(CheckoutCase):
    def crash(self):
        """QGIS dog: projektet pekar mot databasen igen men låset och kopian finns kvar."""
        co._to_database(self.project, self.plan)
        self.project.writeEntry(DB_SCOPE, "checkout_path", "")
        self.project.writeEntry(DB_SCOPE, "checkout_token", "")

    def test_an_interrupted_checkout_can_be_taken_up_again(self):
        path = co.check_out(self.project, self.copies)
        lock = co.read_lock(self.plan)
        self.crash()
        self.assertEqual(co.state(self.project), co.DATABASE)
        self.assertEqual(co.resumable_copy(self.plan, self.copies), (path, lock))
        co.resume(self.project, path, lock)
        self.assertEqual(co.state(self.project), co.LOCAL)
        self.assertFalse(find_layer(self.project, "detaljplan").readOnly())

    def test_nothing_is_resumable_without_a_lock_or_when_the_lock_is_someone_elses(self):
        co.check_out(self.project, self.copies)
        self.assertIsNotNone(co.resumable_copy(self.plan, self.copies))
        co.break_lock(self.plan)
        self.assertIsNone(co.resumable_copy(self.plan, self.copies))
        self.conn.meta["checkout"] = other_lock().to_json()
        self.assertIsNone(co.resumable_copy(self.plan, self.copies))

    def test_copies_of_other_plans_are_not_offered(self):
        co.check_out(self.project, self.copies)
        elsewhere = storage.PostgisStorage("db", "annan_plan", self.conn)
        self.assertEqual(co.local_copies(elsewhere, self.copies), [])
        self.assertEqual(len(co.local_copies(self.plan, self.copies)), 1)

    def test_broken_files_in_the_copies_folder_are_ignored(self):
        self.copies.mkdir(parents=True, exist_ok=True)
        (self.copies / "trasig.gpkg").write_bytes(b"inte en databas")
        self.assertEqual(co.local_copies(self.plan, self.copies), [])
        self.assertEqual(co.local_copies(self.plan, self.dir / "finns_inte"), [])


class SqlTests(unittest.TestCase):
    def test_values_are_written_as_sql_literals_for_their_column_type(self):
        cases = [(None, model.TEXT, "NULL"), ("it's", model.TEXT, "'it''s'"), (5, model.INT, "5"), (5.0, model.INT, "5"),
                 (1.5, model.REAL, "1.5"), (True, model.BOOL, "true"), (0, model.BOOL, "false"),
                 ("x", model.DATE, "'x'")]
        for value, kind, expected in cases:
            self.assertEqual(co.sql_value(value, kind), expected, (value, kind))

    @unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
    def test_dates_null_variants_and_qt_types(self):
        from qgis.core import NULL
        self.assertEqual(co.sql_value(NULL, model.TEXT), "NULL")
        self.assertEqual(co.sql_value(QDate(2024, 3, 1), model.DATE), "'2024-03-01'")
        self.assertEqual(co.sql_value(QDateTime(QDate(2024, 3, 1), __import__("qgis.PyQt.QtCore", fromlist=["QTime"]).QTime(9, 5, 7)),
                                      model.DATETIME), "'2024-03-01 09:05:07'")
        self.assertEqual(co.sql_value(QDate(), model.DATE), "NULL")

    def tables(self, rows_per_table=1):
        detaljplan = model.DETALJPLAN
        row = {"fid": 1, "geom": "MultiPolygon (((0 0, 1 0, 1 1, 0 0)))", **{f.name: None for f in detaljplan.fields}}
        row["namn"] = "Kv 'Väktaren'"
        return [(detaljplan, [dict(row, fid=i + 1) for i in range(rows_per_table)]), (model.DOKUMENT, [])]

    def test_the_statement_is_one_do_block_and_quotes_text(self):
        sql = co.checkin_sql("dp_test", 3006, "a" * 32, self.tables())
        self.assertTrue(sql.startswith("DO $dp$ BEGIN") and sql.endswith("END $dp$"))
        self.assertIn("'Kv ''Väktaren'''", sql)
        self.assertIn("ST_Multi(ST_GeomFromText('MultiPolygon (((0 0, 1 0, 1 1, 0 0)))', 3006))", sql)
        self.assertIn('DELETE FROM "dp_test"."dokument";', sql, "en tom tabell töms också")
        self.assertNotIn('INSERT INTO "dp_test"."dokument"', sql)

    def test_a_row_without_geometry_gets_null(self):
        tables = self.tables()
        tables[0][1][0]["geom"] = None
        self.assertIn("(1, NULL, ", co.checkin_sql("dp_test", 3006, "a" * 32, tables))

    def test_many_rows_are_split_into_batches(self):
        sql = co.checkin_sql("dp_test", 3006, "a" * 32, self.tables(rows_per_table=co.BATCH * 2 + 1))
        self.assertEqual(sql.count('INSERT INTO "dp_test"."detaljplan"'), 3)

    def test_the_dollar_quote_tag_is_changed_if_the_content_contains_it(self):
        tables = self.tables()
        tables[0][1][0]["namn"] = "kostar $dp$ pengar"
        sql = co.checkin_sql("dp_test", 3006, "a" * 32, tables)
        self.assertTrue(sql.startswith("DO $dp1$ BEGIN") and sql.endswith("END $dp1$"))

    def test_the_sequence_is_reset_after_the_rows_are_written(self):
        sql = co.checkin_sql("dp_test", 3006, "a" * 32, self.tables())
        self.assertIn("PERFORM setval(pg_get_serial_sequence('\"dp_test\".\"detaljplan\"', 'fid'), "
                      "COALESCE((SELECT MAX(\"fid\") FROM \"dp_test\".\"detaljplan\"), 1));", sql)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ActionsTests(CheckoutCase):
    def setUp(self):
        super().setUp()
        self.reports = []
        self.refreshed = []
        self.actions = CheckoutActions(self.controller, lambda text, warning=False: self.reports.append((text, warning)),
                                       after=lambda: self.refreshed.append(1))
        self.asked = []

        def yes_no(title, text, yes="Ja", no="Avbryt"):
            self.asked.append(title)
            return self.answer

        self.answer = True
        patcher = mock.patch.object(self.actions, "_ask_yes_no", yes_no)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_checking_out_asks_first_then_reports_and_refreshes(self):
        self.assertTrue(self.actions.check_out())
        self.assertEqual(self.asked, ["Checka ut planen"])
        self.assertEqual(self.actions.state(), co.LOCAL)
        self.assertIn("Checkade ut planen", self.reports[-1][0])
        self.assertEqual(self.refreshed, [1])

    def test_declining_leaves_everything_alone(self):
        self.answer = False
        self.assertFalse(self.actions.check_out())
        self.assertEqual(self.actions.state(), co.DATABASE)
        self.assertIsNone(co.read_lock(self.plan))

    def test_a_plan_that_is_already_checked_out_needs_no_new_checkout(self):
        self.actions.check_out()
        self.asked.clear()
        self.assertTrue(self.actions.check_out())
        self.assertEqual(self.asked, [])

    def test_a_locked_plan_offers_to_break_the_lock_and_can_then_be_checked_out(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        with mock.patch.object(self.actions, "_ask_break_lock", return_value=True) as ask:
            self.assertTrue(self.actions.check_out())
        self.assertEqual(ask.call_args.args[0], other_lock())
        self.assertEqual(self.actions.state(), co.LOCAL)

    def test_a_locked_plan_stays_locked_if_the_lock_is_not_broken(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        with mock.patch.object(self.actions, "_ask_break_lock", return_value=False):
            self.assertFalse(self.actions.check_out())
        self.assertEqual(co.read_lock(self.plan), other_lock())
        self.assertEqual(self.actions.state(), co.DATABASE)

    def test_breaking_the_lock_is_only_tried_once(self):
        self.conn.meta["checkout"] = other_lock().to_json()
        with mock.patch.object(self.actions, "_ask_break_lock", return_value=True) as ask, \
                mock.patch.object(co, "break_lock"):  # låset försvinner inte: någon annan hann före
            self.assertFalse(self.actions.check_out())
        self.assertEqual(ask.call_count, 1)

    def test_an_interrupted_checkout_is_offered_for_resuming(self):
        co.check_out(self.project, self.copies)
        co._to_database(self.project, self.plan)
        self.project.writeEntry(DB_SCOPE, "checkout_path", "")
        self.project.writeEntry(DB_SCOPE, "checkout_token", "")
        self.assertTrue(self.actions.check_out())
        self.assertEqual(self.asked, ["Fortsätt utcheckningen"])
        self.assertEqual(self.actions.state(), co.LOCAL)
        self.assertEqual(len(self.conn.checkins), 0)

    def test_an_edit_session_in_progress_blocks_checkout_and_checkin(self):
        self.controller.attach()
        with mock.patch.object(type(self.controller), "editing", new_callable=mock.PropertyMock, return_value=True):
            self.assertFalse(self.actions.check_out())
            self.assertIn("Avsluta redigeringen", self.reports[-1][0])
        self.actions.check_out()
        with mock.patch.object(type(self.controller), "editing", new_callable=mock.PropertyMock, return_value=True):
            self.assertFalse(self.actions.check_in())
            self.assertIn("Avsluta redigeringen", self.reports[-1][0])

    def test_checking_in_reports_and_returns_the_plan_to_the_database(self):
        self.actions.check_out()
        with mock.patch.object(self.actions, "_ask_check_in", return_value=CHECK_IN):
            self.assertTrue(self.actions.check_in())
        self.assertEqual(self.actions.state(), co.DATABASE)
        self.assertIn("Checkade in planen", self.reports[-1][0])
        self.assertFalse(self.reports[-1][1])
        self.assertEqual(len(self.conn.checkins), 1)

    def test_cancelling_the_checkin_dialog_does_nothing(self):
        self.actions.check_out()
        with mock.patch.object(self.actions, "_ask_check_in", return_value=CANCEL):
            self.assertFalse(self.actions.check_in())
        self.assertEqual(self.actions.state(), co.LOCAL)

    def test_discarding_asks_for_confirmation(self):
        self.actions.check_out()
        self.answer = False
        with mock.patch.object(self.actions, "_ask_check_in", return_value=DISCARD):
            self.assertFalse(self.actions.check_in())
        self.assertEqual(self.actions.state(), co.LOCAL)
        self.answer = True
        with mock.patch.object(self.actions, "_ask_check_in", return_value=DISCARD):
            self.assertTrue(self.actions.check_in())
        self.assertEqual(self.actions.state(), co.DATABASE)
        self.assertIn("Kastade utcheckningen", self.reports[-1][0])
        self.assertEqual(self.conn.checkins, [])

    def test_a_failing_checkin_is_reported_and_the_copy_and_lock_are_kept(self):
        self.actions.check_out()
        self.conn.fail_on = "DO $dp$ BEGIN IF NOT EXISTS"
        with mock.patch.object(self.actions, "_ask_check_in", return_value=CHECK_IN):
            self.assertFalse(self.actions.check_in())
        text, warning = self.reports[-1]
        self.assertTrue(warning)
        self.assertIn("lokala kopia och låset är kvar", text)
        self.assertEqual(self.actions.state(), co.LOCAL)

    def test_a_copy_that_could_not_be_removed_is_reported_with_its_path(self):
        self.actions.check_out()
        with mock.patch.object(self.actions, "_ask_check_in", return_value=CHECK_IN), \
                mock.patch.object(co, "_remove", return_value=False):
            self.assertTrue(self.actions.check_in())
        self.assertIn("kunde inte tas bort", self.reports[-1][0])
        self.assertTrue(self.reports[-1][1])

    def test_a_plan_in_a_file_needs_no_checkout(self):
        with mock.patch.object(co, "_is_db_layer", lambda layer: False):
            self.assertFalse(self.actions.check_out())
            self.assertFalse(self.actions.check_in())
        self.assertIn("behöver inte checkas ut", self.reports[0][0])
        self.assertIn("inte utcheckad", self.reports[1][0])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ToolBarTests(CheckoutCase):
    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)
        self.toolbar.show()
        self.addCleanup(self.toolbar.hide)

    def test_the_button_is_shown_for_database_plans_only_and_changes_with_the_state(self):
        self.toolbar.refresh()
        self.assertTrue(self.toolbar.act_checkout.isVisible())
        self.assertEqual(self.toolbar.act_checkout.text(), "Checka ut")
        self.assertFalse(self.toolbar.act_checkout.icon().isNull())
        co.check_out(self.project, self.copies)
        self.toolbar.refresh()
        self.assertEqual(self.toolbar.act_checkout.text(), "Checka in")
        self.assertIn("Checka in", self.toolbar.act_checkout.toolTip())
        with mock.patch.object(co, "_is_db_layer", lambda layer: False):
            # planen ligger nu i en fil ur pluginets synvinkel
            self.project.writeEntry(DB_SCOPE, "checkout_path", "")
            self.toolbar.refresh()
            self.assertFalse(self.toolbar.act_checkout.isVisible())

    def test_the_button_checks_out_and_then_in(self):
        with mock.patch.object(self.toolbar.checkout, "_ask_yes_no", return_value=True), \
                mock.patch.object(self.toolbar.checkout, "_ask_check_in", return_value=CHECK_IN):
            self.toolbar.act_checkout.trigger()
            self.assertEqual(co.state(self.project), co.LOCAL)
            self.toolbar.act_checkout.trigger()
            self.assertEqual(co.state(self.project), co.DATABASE)
        self.assertEqual(self.toolbar.act_checkout.text(), "Checka ut")

    def test_starting_to_draw_on_a_database_plan_checks_it_out_first(self):
        with mock.patch.object(self.toolbar.checkout, "_ask_yes_no", return_value=True):
            self.toolbar.start()
        self.assertEqual(co.state(self.project), co.LOCAL)
        self.assertTrue(self.controller.editing)

    def test_declining_the_checkout_means_no_editing(self):
        with mock.patch.object(self.toolbar.checkout, "_ask_yes_no", return_value=False):
            self.toolbar.start()
        self.assertFalse(self.controller.editing)
        self.assertEqual(co.state(self.project), co.DATABASE)

    def test_a_database_plan_cannot_be_edited_even_if_the_layers_are_forced_open(self):
        self.assertFalse(self.layers["anvandning_yta"].startEditing())

    def test_refresh_makes_old_projects_read_only(self):
        for layer in self.layers.values():
            layer.setReadOnly(False)
        self.toolbar.refresh()
        self.assertTrue(all(layer.readOnly() for layer in self.layers.values()))

    def test_a_file_plan_starts_editing_without_any_question(self):
        with mock.patch.object(co, "_is_db_layer", lambda layer: False):
            for layer in self.layers.values():
                layer.setReadOnly(False)
            with mock.patch.object(self.toolbar.checkout, "_ask_yes_no") as ask:
                self.toolbar.start()
            ask.assert_not_called()
        self.assertTrue(self.controller.editing)


if __name__ == "__main__":
    unittest.main()
