"""Lagring i PostGIS: SQL, anslutning, dialogrutor och flödet i pluginet.

Ett schema delas numera av flera planer (en ``plan``-kolumn skiljer deras rader åt i samma tabeller); se
``storage.py``. Ingen riktig databas används (ingen finns i testmiljön): databasen ersätts av en låtsasanslutning
som registrerar SQL och håller en enkel modell av schemats och planernas nycklar, och PostGIS-lagren av lager ur en
GeoPackage med samma tabeller. Att SQL:en fungerar mot en riktig PostGIS-databas är alltså inte provat här."""
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS  # noqa: E402

if HAVE_QGIS:
    from osgeo import ogr
    from qgis.core import QgsDataSourceUri, QgsFieldConstraints, QgsProject
    import rita_detaljplan
    from rita_detaljplan.core import geopackage, model, storage
    from rita_detaljplan.core.project import create_postgis_plan_project, find_plan_group, load_plan
    from rita_detaljplan.gui.new_plan_dialog import NewPlanDialog, NewPlanValues
    from rita_detaljplan.gui.postgis_plan_dialog import PostgisPlanDialog
    from test_toolbar import GuiCase
    from plan_case import PlanCase


class FakeConnection:
    """Låtsasanslutning: registrerar SQL och håller en enkel modell av schemats (``dp_schema``) och planernas
    (``dp_meta``) nycklar, per schema."""

    def __init__(self, schemas=("public",), postgis=True, fail_on=None, plugin_schemas=()):
        self.sql = []
        self.schemas = list(schemas)
        self.postgis = postgis
        self.fail_on = fail_on
        self.plugin_schemas = list(plugin_schemas)  # scheman med dp_schema, för list_plugin_schemas
        self.schema_meta = {}  # schema -> {key: value}  (dp_schema)
        self.plan_meta = {}  # schema -> {plan_id: {key: value}}  (dp_meta)

    def uri(self):
        return "dbname='planer' host=localhost port=5432 user='eric' sslmode=disable"

    def executeSql(self, sql):
        self.sql.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("syntaxfel nära " + self.fail_on)
        if "postgis_version" in sql:
            if not self.postgis:
                raise RuntimeError("function postgis_version() does not exist")
            return [["3.4 USE_GEOS=1"]]
        if "information_schema.schemata" in sql:
            return [[s] for s in self.schemas]
        if "information_schema.tables" in sql:
            return [[s] for s in self.plugin_schemas]
        match = re.match(r'SELECT "key", "value" FROM "(\w+)"\."dp_schema"', sql)
        if match:
            return [[k, v] for k, v in self.schema_meta.get(match.group(1), {}).items()]
        match = re.match(r'INSERT INTO "(\w+)"\."dp_schema" \("key", "value"\) VALUES (.+)', sql)
        if match:
            schema = match.group(1)
            for key, value in re.findall(r"\('([^']*)', '([^']*)'\)", match.group(2)):
                self.schema_meta.setdefault(schema, {})[key] = value
            return []
        match = re.match(r'SELECT "key", "value" FROM "(\w+)"\."dp_meta" WHERE "plan" = \'([^\']*)\'', sql)
        if match:
            schema, plan_id = match.groups()
            return [[k, v] for k, v in self.plan_meta.get(schema, {}).get(plan_id, {}).items()]
        match = re.match(r'INSERT INTO "(\w+)"\."dp_meta" \("plan", "key", "value"\) VALUES (.+)', sql)
        if match:
            schema = match.group(1)
            for plan_id, key, value in re.findall(r"\('([^']*)', '([^']*)', '([^']*)'\)", match.group(2)):
                self.plan_meta.setdefault(schema, {}).setdefault(plan_id, {})[key] = value
            return []
        match = re.match(r'SELECT 1 FROM "(\w+)"\."dp_meta" WHERE "plan" = \'([^\']*)\' LIMIT 1', sql)
        if match:
            schema, plan_id = match.groups()
            return [[1]] if plan_id in self.plan_meta.get(schema, {}) else []
        match = re.match(r'SELECT DISTINCT "plan" FROM "(\w+)"\."dp_meta"', sql)
        if match:
            return [[p] for p in sorted(self.plan_meta.get(match.group(1), {}))]
        return []


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class NameTests(unittest.TestCase):
    def test_a_plan_name_becomes_a_safe_schema_name(self):
        self.assertEqual(storage.schema_name("DP 2026:1"), "dp_2026_1")
        self.assertEqual(storage.schema_name("Åkerö Kv. Väktaren"), "akero_kv_vaktaren")
        self.assertEqual(storage.schema_name("2026 Norra"), "dp_2026_norra")
        self.assertEqual(storage.schema_name("  "), "")
        self.assertEqual(len(storage.schema_name("x" * 200)), 63)

    def test_only_simple_lowercase_names_are_valid_schemas(self):
        for good in ("dp_2026_1", "a", "kv_vaktaren"):
            self.assertTrue(storage.is_valid_schema(good), good)
        for bad in ("", "1abc", "Abc", "a-b", "a b", 'a"b', "public", "pg_catalog", "information_schema", "å", "x" * 64):
            self.assertFalse(storage.is_valid_schema(bad), bad)

    def test_plan_ids_follow_the_same_rules_but_public_and_pg_are_fine(self):
        for good in ("dp_2026_1", "a", "public"):
            self.assertTrue(storage.is_valid_plan_id(good), good)
        for bad in ("", "1abc", "Abc", "a-b", "a b", 'a"b'):
            self.assertFalse(storage.is_valid_plan_id(bad), bad)

    def test_quoting_protects_identifiers_and_text(self):
        self.assertEqual(storage.quote('a"b'), '"a""b"')
        self.assertEqual(storage.literal("it's"), "'it''s'")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class SqlTests(unittest.TestCase):
    def setUp(self):
        self.sql = storage.ensure_schema("dp_test", 3010)

    def creates(self, table):
        return [s for s in self.sql if s.startswith(f'CREATE TABLE IF NOT EXISTS "dp_test"."{table}"')]

    def test_the_schema_is_created_first(self):
        self.assertEqual(self.sql[0], 'CREATE SCHEMA IF NOT EXISTS "dp_test"')

    def test_every_layer_of_the_model_becomes_a_table(self):
        for layer_def in model.LAYERS:
            self.assertEqual(len(self.creates(layer_def.name)), 1, layer_def.name)
        self.assertEqual(len(self.creates(model.META_TABLE)), 1)
        self.assertEqual(len(self.creates("dp_schema")), 1)

    def test_every_table_has_a_plan_column_except_the_schema_wide_one(self):
        for layer_def in model.LAYERS:
            self.assertIn('"plan" text NOT NULL', self.creates(layer_def.name)[0])
        self.assertIn('"plan" text NOT NULL', self.creates(model.META_TABLE)[0])
        self.assertNotIn('"plan"', self.creates("dp_schema")[0])

    def test_every_field_is_a_quoted_column_with_a_fitting_type(self):
        for layer_def in model.LAYERS:
            ddl = self.creates(layer_def.name)[0]
            self.assertIn('"fid" serial PRIMARY KEY', ddl)
            for field in layer_def.fields:
                self.assertIn(f'"{field.name}" ', ddl, f"{layer_def.name}.{field.name}")
        area = self.creates("anvandning_yta")[0]
        self.assertIn('"versionGiltigFran" timestamp', area)
        self.assertIn('"label_x" double precision', area)
        self.assertIn('"bestammelser" integer', area)
        self.assertIn('"avviker" boolean', self.creates("bestammelse")[0])
        self.assertIn('"datumPaborjat" date', self.creates("beslutsinformation")[0])

    def test_geometry_columns_carry_type_and_coordinate_system(self):
        self.assertIn('"geom" geometry(MultiPolygon, 3010)', self.creates("detaljplan")[0])
        self.assertIn('"geom" geometry(MultiLineString, 3010)', self.creates("hjalplinje")[0])
        self.assertNotIn("geometry(", self.creates("bestammelse")[0])

    def test_spatial_tables_get_a_spatial_index_and_every_table_a_plan_index(self):
        geom_indexes = [s for s in self.sql if "gist" in s]
        self.assertEqual(len(geom_indexes), sum(1 for d in model.LAYERS if d.geometry))
        plan_indexes = [s for s in self.sql if "_plan_idx" in s]
        self.assertEqual(len(plan_indexes), len(model.LAYERS))

    def test_nothing_in_the_ddl_is_left_unquoted_or_leaks_into_other_schemas(self):
        for statement in self.sql[1:]:
            if statement.startswith(("CREATE TABLE", "COMMENT", "CREATE INDEX", "CREATE UNIQUE INDEX")):
                self.assertIn('"dp_test".', statement)

    def test_the_ddl_is_idempotent_if_not_exists_everywhere(self):
        for statement in self.sql:
            if statement.startswith("CREATE TABLE"):
                self.assertIn("IF NOT EXISTS", statement)
            if statement.startswith("CREATE INDEX") or statement.startswith("CREATE UNIQUE INDEX"):
                self.assertIn("IF NOT EXISTS", statement)

    def test_upgrade_from_schema_3_adds_everything_and_sets_the_version(self):
        sql = storage.postgis_upgrade("dp_test", 3, 3006)
        text = "\n".join(sql)
        self.assertIn('CREATE TABLE IF NOT EXISTS "dp_test"."hjalplinje"', text)
        self.assertEqual(text.count('ADD COLUMN IF NOT EXISTS "label_x"'), 3)
        self.assertEqual(text.count('ADD COLUMN IF NOT EXISTS "label_w"'), 3)
        self.assertIn('"egenskap_yta" ADD COLUMN IF NOT EXISTS "sekundar"', text)
        self.assertIn('"bestammelse" ADD COLUMN IF NOT EXISTS "ordning"', text)
        self.assertIn(f'"dp_schema" SET "value" = \'{model.SCHEMA_VERSION}\'', sql[-1])

    def test_upgrade_from_schema_5_adds_the_order_column_and_the_schema_7_columns_only(self):
        sql = storage.postgis_upgrade("dp_test", 5, 3006)
        text = " ".join(sql)
        self.assertIn('"ordning"', sql[0])
        self.assertEqual(text.count('"label_w"'), 3)
        self.assertEqual(text.count('"sekundar"'), 1)
        self.assertNotIn('"label_x"', text)
        self.assertEqual(len(sql), 6)

    def test_upgrade_from_schema_6_only_adds_the_schema_7_columns(self):
        sql = storage.postgis_upgrade("dp_test", 6, 3006)
        self.assertEqual(len(sql), 5)
        self.assertNotIn('"ordning"', " ".join(sql))
        self.assertIn(f'"dp_schema" SET "value" = \'{model.SCHEMA_VERSION}\'', sql[-1])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CreateTests(unittest.TestCase):
    def create(self, connection, schema="dp_test", plan_id="dp_1", epsg=3006):
        return storage.create_postgis_plan("db", schema, plan_id, epsg, {"kommun": "Eskilstuna", "kommunkod": "0484"},
                                           connection)

    def test_creating_a_plan_in_a_new_schema_runs_the_checks_and_then_the_ddl(self):
        conn = FakeConnection()
        plan = self.create(conn)
        self.assertEqual((plan.connection_name, plan.schema, plan.plan_id), ("db", "dp_test", "dp_1"))
        self.assertIn("postgis_version", conn.sql[0])
        self.assertIn('"dp_schema"', conn.sql[1], "kollar om schemat redan finns innan det skapas")
        self.assertEqual(conn.sql[2], 'CREATE SCHEMA IF NOT EXISTS "dp_test"')
        self.assertEqual(conn.schema_meta["dp_test"], {"schema_version": str(model.SCHEMA_VERSION), "epsg": "3006"})
        self.assertEqual(conn.plan_meta["dp_test"]["dp_1"]["kommun"], "Eskilstuna")
        self.assertEqual(conn.plan_meta["dp_test"]["dp_1"]["spec_version"], model.SPEC_VERSION)

    def test_a_second_plan_in_the_same_schema_only_adds_its_own_rows(self):
        conn = FakeConnection()
        self.create(conn, plan_id="dp_1")
        before = list(conn.sql)
        self.create(conn, plan_id="dp_2")
        after = conn.sql[len(before):]
        self.assertFalse(any(s.startswith("CREATE SCHEMA") and "IF NOT EXISTS" not in s for s in after))
        self.assertEqual(set(conn.plan_meta["dp_test"]), {"dp_1", "dp_2"})

    def test_a_mismatched_coordinate_system_in_an_existing_schema_is_refused(self):
        conn = FakeConnection()
        self.create(conn, plan_id="dp_1", epsg=3006)
        with self.assertRaisesRegex(storage.PostgisError, "EPSG:3006"):
            self.create(conn, plan_id="dp_2", epsg=3010)
        self.assertNotIn("dp_2", conn.plan_meta.get("dp_test", {}))

    def test_a_duplicate_plan_id_in_the_same_schema_is_refused(self):
        conn = FakeConnection()
        self.create(conn, plan_id="dp_1")
        with self.assertRaisesRegex(storage.PostgisError, "dp_1"):
            self.create(conn, plan_id="dp_1")

    def test_a_database_without_postgis_is_explained(self):
        conn = FakeConnection(postgis=False)
        with self.assertRaisesRegex(storage.PostgisError, "PostGIS"):
            self.create(conn)
        self.assertFalse(any(s.startswith("CREATE") for s in conn.sql))

    def test_a_bad_schema_plan_name_or_projection_is_rejected_before_any_sql(self):
        conn = FakeConnection()
        with self.assertRaises(storage.PostgisError):
            self.create(conn, schema="Bad Name")
        with self.assertRaises(storage.PostgisError):
            self.create(conn, plan_id="Bad Name")
        with self.assertRaises(ValueError):
            self.create(conn, epsg=3857)
        self.assertEqual(conn.sql, [])

    def test_a_failure_in_a_brand_new_schema_removes_it_and_reports(self):
        conn = FakeConnection(fail_on='CREATE TABLE IF NOT EXISTS "dp_test"."bestammelse"')
        with self.assertRaisesRegex(storage.PostgisError, "syntaxfel"):
            self.create(conn)
        self.assertEqual(conn.sql[-1], 'DROP SCHEMA IF EXISTS "dp_test" CASCADE')

    def test_a_failure_in_an_existing_schema_does_not_drop_it(self):
        conn = FakeConnection()
        self.create(conn, plan_id="dp_1")
        conn.fail_on = 'CREATE TABLE IF NOT EXISTS "dp_test"."bestammelse"'
        with self.assertRaisesRegex(storage.PostgisError, "syntaxfel"):
            self.create(conn, plan_id="dp_2")
        self.assertFalse(any(s.startswith("DROP SCHEMA") for s in conn.sql))

    def test_the_connection_error_is_wrapped_for_the_user(self):
        conn = FakeConnection()
        conn.executeSql = mock.Mock(side_effect=RuntimeError("could not connect"))
        with self.assertRaises(storage.PostgisError) as caught:
            self.create(conn)
        self.assertIn("could not connect", str(caught.exception))

    def test_schemas_with_the_plugins_tables_are_found(self):
        conn = FakeConnection(plugin_schemas=["dp_a", "dp_b"])
        self.assertEqual(storage.list_plugin_schemas(conn), ["dp_a", "dp_b"])
        broken = mock.Mock()
        broken.executeSql.side_effect = RuntimeError("nej")
        with self.assertRaises(storage.PostgisError):
            storage.list_plugin_schemas(broken)

    def test_the_plans_of_a_schema_are_listed(self):
        conn = FakeConnection()
        self.create(conn, plan_id="dp_b")
        self.create(conn, plan_id="dp_a")
        self.assertEqual(storage.list_plans_in_schema(conn, "dp_test"), ["dp_a", "dp_b"])

    def test_plan_exists_reflects_what_was_created(self):
        conn = FakeConnection()
        self.create(conn, plan_id="dp_1")
        self.assertTrue(storage.plan_exists(conn, "dp_test", "dp_1"))
        self.assertFalse(storage.plan_exists(conn, "dp_test", "dp_2"))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class StorageTests(unittest.TestCase):
    def test_a_layer_uri_points_at_the_schema_table_key_geometry_and_the_plan_filter(self):
        plan = storage.PostgisStorage("db", "dp_test", "dp_1", FakeConnection())
        uri = QgsDataSourceUri(plan.layer_uri(model.ANVANDNING_YTA, 3010))
        self.assertEqual((uri.database(), uri.host(), uri.schema(), uri.table(), uri.keyColumn(), uri.geometryColumn()),
                         ("planer", "localhost", "dp_test", "anvandning_yta", "fid", "geom"))
        self.assertEqual(uri.srid(), "3010")
        self.assertEqual(uri.sql(), '"plan" = \'dp_1\'')
        plain = QgsDataSourceUri(plan.layer_uri(model.BESTAMMELSE))
        self.assertEqual((plain.table(), plain.geometryColumn()), ("bestammelse", ""))

    def test_the_meta_is_read_from_the_database_and_merged_with_the_schemas_own_keys(self):
        conn = FakeConnection()
        conn.plan_meta["dp_test"] = {"dp_1": {"kommun": "Eskilstuna"}}
        conn.schema_meta["dp_test"] = {"schema_version": "6", "epsg": "3006"}
        self.assertEqual(storage.PostgisStorage("db", "dp_test", "dp_1", conn).read_meta(),
                         {"kommun": "Eskilstuna", "schema_version": "6", "epsg": "3006"})
        broken = mock.Mock()
        broken.executeSql.side_effect = RuntimeError('relation "x.dp_meta" does not exist')
        self.assertEqual(storage.PostgisStorage("db", "x", "dp_1", broken).read_meta(), {})

    def test_an_unknown_plan_id_in_a_real_schema_gives_an_empty_meta(self):
        conn = FakeConnection()
        conn.schema_meta["dp_test"] = {"schema_version": str(model.SCHEMA_VERSION), "epsg": "3006"}
        self.assertEqual(storage.PostgisStorage("db", "dp_test", "saknas", conn).read_meta(), {})

    def test_an_old_schema_is_upgraded_through_sql(self):
        conn = FakeConnection()
        conn.schema_meta["dp_test"] = {"schema_version": "5", "epsg": "3006"}
        self.assertTrue(storage.PostgisStorage("db", "dp_test", "dp_1", conn).upgrade())
        self.assertTrue(any('"ordning"' in s for s in conn.sql))

    def test_a_current_schema_is_left_alone(self):
        conn = FakeConnection()
        conn.schema_meta["dp_test"] = {"schema_version": str(model.SCHEMA_VERSION), "epsg": "3006"}
        self.assertFalse(storage.PostgisStorage("db", "dp_test", "dp_1", conn).upgrade())
        self.assertFalse(any(s.startswith(("ALTER", "UPDATE", "CREATE")) for s in conn.sql))

    def test_a_missing_connection_is_reported(self):
        with mock.patch.object(storage, "postgis_connections", return_value={}):
            with self.assertRaisesRegex(storage.PostgisError, "finns inte i QGIS"):
                storage.PostgisStorage("saknas", "dp", "dp_1").connection

    def test_storages_compare_by_connection_schema_and_plan(self):
        self.assertEqual(storage.PostgisStorage("db", "a", "p"), storage.PostgisStorage("db", "a", "p"))
        self.assertNotEqual(storage.PostgisStorage("db", "a", "p"), storage.PostgisStorage("db", "a", "q"))
        self.assertNotEqual(storage.PostgisStorage("db", "a", "p"), storage.PostgisStorage("db", "b", "p"))
        self.assertEqual(storage.as_storage("x/plan.gpkg"), storage.GeoPackageStorage("x/plan.gpkg"))
        plan = storage.PostgisStorage("db", "a", "p")
        self.assertIs(storage.as_storage(plan), plan)

    def test_the_name_is_the_plan_id_not_the_schema(self):
        self.assertEqual(storage.PostgisStorage("db", "delat_schema", "min_plan").name, "min_plan")


def gpkg_backed(gpkg):
    """Ersätter PostGIS-lagren med lager ur en GeoPackage med samma tabeller (se modulens beskrivning)."""
    from qgis.core import QgsVectorLayer

    def open_layer(storage_self, uri, alias):
        table = QgsDataSourceUri(uri).table()
        return QgsVectorLayer(f"{Path(gpkg).as_posix()}|layername={table}", alias, "ogr")

    return open_layer


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LoadTests(PlanCase):
    def setUp(self):
        super().setUp()
        self.backing = self.dir / "backing.gpkg"
        geopackage.create_geopackage(self.backing, 3006, {"kommun": "Eskilstuna", "kommunkod": "0484"})
        self.conn = FakeConnection()
        meta = geopackage.read_meta(self.backing)
        self.conn.schema_meta["dp_test"] = {"schema_version": meta["schema_version"], "epsg": meta["epsg"]}
        self.conn.plan_meta["dp_test"] = {"dp_1": {k: v for k, v in meta.items()
                                                    if k not in ("schema_version", "epsg")}}
        patcher = mock.patch.object(storage.PostgisStorage, "_open", gpkg_backed(self.backing))
        patcher.start()
        self.addCleanup(patcher.stop)

    def plan(self):
        return storage.PostgisStorage("db", "dp_test", "dp_1", self.conn)

    def test_a_postgis_plan_loads_like_a_file_plan(self):
        project = QgsProject()
        layers = load_plan(self.plan(), project)
        self.assertEqual(set(layers), {d.name for d in model.LAYERS})
        group = find_plan_group(project)
        self.assertEqual(group.name(), "dp_1", "gruppen heter som plan-id:t tills planen fått ett namn")
        self.assertFalse(group.isExpanded())
        self.assertEqual(len(project.relationManager().relations()), len(model.RELATIONS))
        self.assertTrue(project.snappingConfig().enabled())

    def test_the_layers_get_the_same_configuration_as_for_a_file(self):
        project = QgsProject()
        layers = load_plan(self.plan(), project)
        self.assertEqual(layers["anvandning_yta"].fields().field("objektidentitet").constraints().constraintStrength(
            QgsFieldConstraints.Constraint.ConstraintUnique), QgsFieldConstraints.ConstraintStrength.ConstraintStrengthHard)
        self.assertEqual(layers["anvandning_yta"].defaultValueDefinition(
            layers["anvandning_yta"].fields().indexOf("objektidentitet")).expression(), model.UUID_EXPR)
        self.assertEqual(layers["anvandning_yta"].renderer().referenceScale(), 1000)
        self.assertEqual(layers["hjalplinje"].customProperty("detaljplan_ngp/table"), "hjalplinje")

    def test_a_plan_id_without_metadata_rows_is_not_a_plan(self):
        with self.assertRaisesRegex(ValueError, "inte en detaljplan"):
            load_plan(storage.PostgisStorage("db", "dp_test", "saknas", self.conn), QgsProject())

    def test_an_unreadable_table_is_reported_with_its_name(self):
        with mock.patch.object(storage.PostgisStorage, "_open",
                               lambda self_, uri, alias: __import__("qgis.core", fromlist=["QgsVectorLayer"]).QgsVectorLayer(
                                   "nonsense", alias, "ogr")):
            with self.assertRaisesRegex(ValueError, "Kunde inte läsa tabellen"):
                load_plan(self.plan(), QgsProject())

    def test_creating_a_project_for_a_postgis_plan_writes_a_project_that_points_at_the_database(self):
        conn = FakeConnection()
        plan, qgz = create_postgis_plan_project(self.dir / "proj", "dp_test", "db", "dp_test", "dp_1", "Eskilstuna",
                                                "0484", 3006, conn)
        self.assertEqual(plan, storage.PostgisStorage("db", "dp_test", "dp_1"))
        self.assertTrue(qgz.exists())
        self.assertFalse((self.dir / "proj" / "dp_test.gpkg").exists(), "ingen lokal GeoPackage skapas")
        self.assertEqual(conn.plan_meta["dp_test"]["dp_1"]["kommun"], "Eskilstuna")

    def test_a_second_plan_reuses_the_schema_the_first_one_created(self):
        conn = FakeConnection()
        create_postgis_plan_project(self.dir / "proj", "dp_a", "db", "dp_test", "dp_a", "Eskilstuna", "0484", 3006,
                                    conn)
        create_postgis_plan_project(self.dir / "proj2", "dp_b", "db", "dp_test", "dp_b", "Eskilstuna", "0484", 3006,
                                    conn)
        self.assertEqual(set(conn.plan_meta["dp_test"]), {"dp_a", "dp_b"})

    def test_an_existing_project_file_stops_the_creation_before_the_database_is_touched(self):
        (self.dir / "proj").mkdir()
        (self.dir / "proj" / "dp_test.qgz").write_bytes(b"")
        conn = FakeConnection()
        with self.assertRaises(FileExistsError):
            create_postgis_plan_project(self.dir / "proj", "dp_test", "db", "dp_test", "dp_1", "E", "0001", 3006, conn)
        self.assertEqual(conn.sql, [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class UpgradeFileTests(unittest.TestCase):
    def test_a_schema_5_file_plan_gets_the_order_column(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            gpkg = geopackage.create_geopackage(Path(tmp) / "gammal.gpkg", 3006, {"kommun": "E"})
            ds = ogr.Open(str(gpkg), 1)
            layer = ds.GetLayerByName("bestammelse")
            layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("ordning"))
            ds = None
            con = sqlite3.connect(str(gpkg))
            con.execute("UPDATE dp_meta SET value='5' WHERE key='schema_version'")
            con.commit()
            con.close()
            project = QgsProject()
            layers = load_plan(gpkg, project)
            self.assertGreaterEqual(layers["bestammelse"].fields().indexOf("ordning"), 0)
            self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class NewPlanDialogPostgisTests(PlanCase):
    def dialog(self, connections):
        with mock.patch.object(storage, "postgis_connections", return_value=connections):
            dialog = NewPlanDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def fill(self, dialog):
        dialog.kommun.set_kommun("Eskilstuna")
        dialog.planbeteckning.setText("Kv Väktaren 1:2")
        dialog.folder.setFilePath("C:/planer")

    def test_without_connections_the_database_choice_is_disabled_and_explained(self):
        dialog = self.dialog({})
        self.assertFalse(dialog.use_postgis.isEnabled())
        self.assertIn("PostgreSQL-anslutningar", dialog.use_postgis.toolTip())
        self.assertTrue(dialog.use_file.isChecked())
        self.fill(dialog)
        self.assertTrue(dialog.is_valid())
        self.assertEqual(dialog.values().kind, "geopackage")

    def test_a_local_file_is_the_default_and_hides_the_database_fields(self):
        dialog = self.dialog({"planer": FakeConnection()})
        self.fill(dialog)
        self.assertTrue(dialog.use_file.isChecked())
        self.assertFalse(dialog.postgis_box.isVisibleTo(dialog))
        values = dialog.values()
        self.assertEqual((values.kind, values.connection, values.schema, values.plan), ("geopackage", "", "", ""))

    def test_choosing_postgis_shows_connections_and_a_shared_schema_suggestion(self):
        dialog = self.dialog({"planer": FakeConnection(), "test": FakeConnection()})
        self.fill(dialog)
        dialog.use_postgis.setChecked(True)
        self.assertTrue(dialog.postgis_box.isVisibleTo(dialog))
        self.assertEqual([dialog.connection.itemText(i) for i in range(dialog.connection.count())], ["planer", "test"])
        self.assertEqual(dialog.schema.text(), "detaljplaner", "schemat föreslås en gång, oberoende av plannamnet")
        dialog.planbeteckning.setText("DP 5")
        self.assertEqual(dialog.schema.text(), "detaljplaner", "schemaförslaget följer inte namnet")

    def test_the_plan_id_is_suggested_from_the_plan_name(self):
        dialog = self.dialog({"planer": FakeConnection()})
        self.fill(dialog)
        dialog.use_postgis.setChecked(True)
        self.assertEqual(dialog.plan.text(), "kv_vaktaren_1_2")
        dialog.planbeteckning.setText("DP 5")
        self.assertEqual(dialog.plan.text(), "dp_5", "plan-id-förslaget följer namnet")

    def test_a_schema_or_plan_id_typed_by_the_user_is_not_overwritten(self):
        dialog = self.dialog({"planer": FakeConnection()})
        dialog.use_postgis.setChecked(True)
        dialog.schema.textEdited.emit("mitt_schema")
        dialog.schema.setText("mitt_schema")
        dialog.plan.textEdited.emit("min_plan")
        dialog.plan.setText("min_plan")
        dialog.planbeteckning.setText("Något helt annat")
        self.assertEqual(dialog.schema.text(), "mitt_schema")
        self.assertEqual(dialog.plan.text(), "min_plan")

    def test_the_values_carry_the_database_choice(self):
        dialog = self.dialog({"planer": FakeConnection()})
        self.fill(dialog)
        dialog.use_postgis.setChecked(True)
        values = dialog.values()
        self.assertEqual((values.kind, values.connection, values.schema, values.plan),
                         ("postgis", "planer", "detaljplaner", "kv_vaktaren_1_2"))
        self.assertEqual(values.directory, Path("C:/planer"), "projektfilen ligger i mappen")

    def test_an_invalid_schema_or_plan_id_blocks_creation(self):
        dialog = self.dialog({"planer": FakeConnection()})
        self.fill(dialog)
        dialog.use_postgis.setChecked(True)
        self.assertTrue(dialog.is_valid())
        dialog.schema.setText("Ogiltigt Namn")
        self.assertFalse(dialog.is_valid())
        dialog.schema.setText("public")
        self.assertFalse(dialog.is_valid())
        dialog.schema.setText("detaljplaner")
        dialog.plan.setText("Ogiltigt Namn")
        self.assertFalse(dialog.is_valid())
        dialog.use_file.setChecked(True)
        self.assertTrue(dialog.is_valid(), "schema och plan-id spelar ingen roll för en lokal fil")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class OpenDialogTests(PlanCase):
    def dialog(self, connections):
        dialog = PostgisPlanDialog(None, connections)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def with_plans(self, schema, plan_ids, conn=None):
        conn = conn or FakeConnection(plugin_schemas=[schema])
        conn.plugin_schemas = list(dict.fromkeys([*conn.plugin_schemas, schema]))
        conn.plan_meta.setdefault(schema, {})
        for plan_id in plan_ids:
            conn.plan_meta[schema][plan_id] = {"kommun": "Eskilstuna"}
        return conn

    def test_the_schemas_of_the_chosen_connection_are_listed(self):
        a = self.with_plans("dp_a", ["p1"])
        b = self.with_plans("dp_b", ["p9"])
        dialog = self.dialog({"a": a, "b": b})
        self.assertEqual([dialog.schema.itemText(i) for i in range(dialog.schema.count())], ["dp_a"])
        dialog.connection.setCurrentIndex(1)
        self.assertEqual([dialog.schema.itemText(i) for i in range(dialog.schema.count())], ["dp_b"])

    def test_the_plans_of_the_chosen_schema_are_listed(self):
        conn = self.with_plans("dp_shared", ["p1", "p2"])
        dialog = self.dialog({"a": conn})
        self.assertEqual([dialog.plans.item(i).text() for i in range(dialog.plans.count())], ["p1", "p2"])
        self.assertIsNone(dialog.selection())
        self.assertFalse(dialog.buttons.buttons()[0].isEnabled())

    def test_selecting_a_plan_enables_opening_and_gives_connection_schema_and_plan(self):
        conn = self.with_plans("dp_shared", ["p1", "p2"])
        dialog = self.dialog({"a": conn})
        dialog.plans.setCurrentRow(1)
        self.assertEqual(dialog.selection(), ("a", "dp_shared", "p2"))
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())

    def test_an_empty_database_and_a_failing_one_are_explained(self):
        self.assertIn("inga scheman", self.dialog({"a": FakeConnection()}).error.text())
        broken = mock.Mock()
        broken.executeSql.side_effect = RuntimeError("timeout")
        dialog = self.dialog({"a": broken})
        self.assertIn("timeout", dialog.error.text())
        self.assertEqual(dialog.plans.count(), 0)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PluginTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.plugin = rita_detaljplan.classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)

    def critical(self):
        return [c.args[1] for c in self.iface.messageBar().pushCritical.call_args_list]

    def test_a_new_postgis_plan_is_created_through_the_database_route(self):
        values = NewPlanValues(self.dir / "ny", "ny_plan", "Eskilstuna", "0484", 3006, "postgis", "planer",
                               "detaljplaner", "ny_plan")
        with mock.patch("rita_detaljplan.plugin.NewPlanDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.create_postgis_plan_project",
                           return_value=(mock.Mock(), self.dir / "ny" / "ny_plan.qgz")) as create, \
                mock.patch("rita_detaljplan.plugin.load_plan") as load:
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.values.return_value = values
            self.plugin.new_plan()
        create.assert_called_once_with(self.dir / "ny", "ny_plan", "planer", "detaljplaner", "ny_plan", "Eskilstuna",
                                       "0484", 3006)
        load.assert_called_once()  # planen läggs till i den öppna kartan i stället för att ersätta projektet
        self.iface.addProject.assert_not_called()
        self.assertFalse((self.dir / "ny" / "ny_plan.gpkg").exists())

    def test_a_database_error_is_shown_and_nothing_is_opened(self):
        values = NewPlanValues(self.dir / "ny", "ny_plan", "Eskilstuna", "0484", 3006, "postgis", "planer",
                               "detaljplaner", "ny_plan")
        with mock.patch("rita_detaljplan.plugin.NewPlanDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.create_postgis_plan_project",
                           side_effect=storage.PostgisError("Det finns redan en plan med den identifieraren")):
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.values.return_value = values
            self.plugin.new_plan()
        self.assertTrue(any("i databasen" in t and "finns redan en plan" in t for t in self.critical()), self.critical())
        self.iface.addProject.assert_not_called()

    def test_open_goes_straight_to_the_file_dialog_when_there_are_no_connections(self):
        with mock.patch.object(storage, "postgis_connections", return_value={}), \
                mock.patch.object(self.plugin, "open_plan_file") as open_file:
            self.plugin.open_plan()
        open_file.assert_called_once()

    def test_open_offers_a_choice_when_there_are_connections(self):
        for index, target in ((0, "open_plan_file"), (1, "open_plan_postgis")):
            with mock.patch.object(storage, "postgis_connections", return_value={"db": FakeConnection()}), \
                    mock.patch("rita_detaljplan.plugin.QMenu") as menu_cls, \
                    mock.patch.object(self.plugin, "open_plan_file") as open_file, \
                    mock.patch.object(self.plugin, "open_plan_postgis") as open_db:
                actions = [object(), object()]
                menu_cls.return_value.addAction.side_effect = actions
                menu_cls.return_value.exec.return_value = actions[index]
                self.plugin.open_plan()
            called = {"open_plan_file": open_file, "open_plan_postgis": open_db}
            called[target].assert_called_once()
            other = open_db if target == "open_plan_file" else open_file
            other.assert_not_called()

    def test_opening_a_postgis_plan_loads_it_into_the_project(self):
        with mock.patch("rita_detaljplan.plugin.PostgisPlanDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.load_plan") as load:
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.selection.return_value = ("planer", "dp_shared", "dp_1")
            self.plugin.open_plan_postgis()
        self.assertEqual(load.call_args.args[0], storage.PostgisStorage("planer", "dp_shared", "dp_1"))

    def test_opening_a_postgis_plan_keeps_a_previously_loaded_plan_loaded(self):
        # flera planer kan vara laddade samtidigt (se core.project.plan_groups/activate_plan_group): den gamla
        # planens lager ska inte tas bort bara för att en ny öppnas (se test_toolbar.
        # test_opening_a_plan_keeps_other_layers_and_plans_but_makes_the_new_one_active för det riktiga flödet,
        # med en verklig GeoPackage-plan – här räcker det att bevisa att ``remove_plan`` inte längre anropas).
        old_plan_layer_id = self.layers["detaljplan"].id()
        with mock.patch("rita_detaljplan.plugin.PostgisPlanDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.load_plan") as load:
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.selection.return_value = ("planer", "dp_shared", "dp_1")
            self.plugin.open_plan_postgis()
        load.assert_called_once()
        self.assertIn(old_plan_layer_id, QgsProject.instance().mapLayers(), "den gamla planens lager ligger kvar")

    def test_a_plan_that_cannot_be_read_is_reported(self):
        with mock.patch("rita_detaljplan.plugin.PostgisPlanDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.load_plan", side_effect=storage.PostgisError("ingen kontakt")):
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.selection.return_value = ("planer", "dp_shared", "dp_1")
            self.plugin.open_plan_postgis()
        self.assertTrue(any("ingen kontakt" in t for t in self.critical()))


if __name__ == "__main__":
    unittest.main()
