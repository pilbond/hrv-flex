import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from hrv_app import polar_auth_v4 as auth


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)
        self.reason = "Unauthorized" if status_code == 401 else "OK"

    def json(self):
        return self._payload


class BuildAuthUrlV4Tests(unittest.TestCase):
    def test_url_contains_endpoint_params_and_state(self):
        url = auth.build_auth_url_v4("cid", "https://app/auth/callback", "sleep:read nightly_recharge:read", "st4te")
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", auth.AUTH_URL_V4)
        self.assertEqual(qs["response_type"], ["code"])
        self.assertEqual(qs["client_id"], ["cid"])
        self.assertEqual(qs["redirect_uri"], ["https://app/auth/callback"])
        self.assertEqual(qs["scope"], ["sleep:read nightly_recharge:read"])
        self.assertEqual(qs["state"], ["st4te"])


class TokenRequestTests(unittest.TestCase):
    def test_exchange_posts_authorization_code_grant(self):
        captured = {}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured.update({"url": url, "headers": headers, "data": data})
            return _FakeResponse(payload={"access_token": "at", "refresh_token": "rt", "expires_in": 43199})

        with patch.object(auth.requests, "post", side_effect=fake_post):
            result = auth.exchange_code_for_token_v4("c0de", "cid", "sec", "https://app/cb")

        self.assertEqual(captured["url"], auth.TOKEN_URL_V4)
        self.assertEqual(captured["data"]["grant_type"], "authorization_code")
        self.assertEqual(captured["data"]["code"], "c0de")
        self.assertEqual(captured["data"]["redirect_uri"], "https://app/cb")
        self.assertTrue(captured["headers"]["Authorization"].startswith("Basic "))
        self.assertEqual(result["access_token"], "at")

    def test_refresh_posts_refresh_token_grant(self):
        captured = {}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured.update({"url": url, "data": data})
            return _FakeResponse(payload={"access_token": "at2", "expires_in": 43199})

        with patch.object(auth.requests, "post", side_effect=fake_post):
            auth.refresh_access_token_v4("rt", "cid", "sec")

        self.assertEqual(captured["url"], auth.TOKEN_URL_V4)
        self.assertEqual(captured["data"], {"grant_type": "refresh_token", "refresh_token": "rt"})

    def test_2xx_without_access_token_raises(self):
        # Un 200 sin access_token no es un grant: persistirlo dejaría un
        # bundle vacío y el callback reportaría éxito sin credenciales.
        with patch.object(auth.requests, "post", return_value=_FakeResponse(payload={"jti": "x"})):
            with self.assertRaises(auth.PolarAuthV4Error) as ctx:
                auth.exchange_code_for_token_v4("c0de", "cid", "sec", "https://app/cb")
        self.assertIn("sin access_token", str(ctx.exception))

    def test_exchange_without_refresh_token_raises_typed(self):
        # v4 exige refresh_token en authorization_code: sin él, el bundle
        # moriría en silencio a las ~12h con el callback habiendo reportado
        # éxito. Debe fallar tipado antes de persistir nada.
        with patch.object(auth.requests, "post",
                          return_value=_FakeResponse(payload={"access_token": "at-secreto", "expires_in": 43199})):
            with self.assertRaises(auth.PolarAuthV4Error) as ctx:
                auth.exchange_code_for_token_v4("c0de", "cid", "sec", "https://app/cb")
        self.assertIn("refresh_token", str(ctx.exception))
        self.assertNotIn("at-secreto", str(ctx.exception))

    def test_refresh_without_refresh_token_in_response_is_valid(self):
        # En refresh la omisión de refresh_token es rotación legítima (se
        # conserva el previo); no debe aplicarse la exigencia del exchange.
        with patch.object(auth.requests, "post",
                          return_value=_FakeResponse(payload={"access_token": "at2", "expires_in": 43199})):
            result = auth.refresh_access_token_v4("rt", "cid", "sec")
        self.assertEqual(result["access_token"], "at2")

    def test_token_error_raises_without_tokens(self):
        with patch.object(auth.requests, "post", return_value=_FakeResponse(400, text="invalid_grant")):
            with self.assertRaises(auth.PolarAuthV4Error) as ctx:
                auth.refresh_access_token_v4("rt-secreto", "cid", "sec")
        self.assertNotIn("rt-secreto", str(ctx.exception))


class BundleTests(unittest.TestCase):
    def test_make_bundle_sets_metadata_and_preserves_previous(self):
        previous = {"refresh_token": "rt-old", "x_user_id": "u1"}
        bundle = auth.make_bundle(
            {"access_token": "at2", "expires_in": 43199}, scopes="sleep:read", previous=previous, refresh=True
        )
        self.assertEqual(bundle["provider_version"], "v4")
        self.assertEqual(bundle["scopes"], "sleep:read")
        self.assertEqual(bundle["refresh_token"], "rt-old")
        self.assertEqual(bundle["x_user_id"], "u1")
        self.assertAlmostEqual(bundle["obtained_at"], time.time(), delta=5)

    def test_make_bundle_exchange_does_not_inherit_old_refresh_token(self):
        # Un exchange es un grant NUEVO: heredar el refresh_token del grant
        # anterior (posiblemente revocado) crearía un bundle híbrido
        # access-nuevo/refresh-viejo. x_user_id sí se preserva.
        previous = {"refresh_token": "rt-old", "x_user_id": "u1"}
        bundle = auth.make_bundle(
            {"access_token": "at2", "expires_in": 43199}, scopes="sleep:read", previous=previous
        )
        self.assertNotIn("refresh_token", bundle)
        self.assertEqual(bundle["x_user_id"], "u1")

    def test_make_bundle_prefers_granted_scope_from_response(self):
        bundle = auth.make_bundle({"access_token": "at", "scope": "sleep:read"}, scopes="sleep:read tests:read")
        self.assertEqual(bundle["scopes"], "sleep:read")

    def test_make_bundle_initial_exchange_without_scope_falls_back_to_requested(self):
        # Exchange inicial (sin previous): si la respuesta omite `scope`, el
        # RFC 6749 dice "omission = as requested".
        bundle = auth.make_bundle({"access_token": "at"}, scopes="sleep:read tests:read")
        self.assertEqual(bundle["scopes"], "sleep:read tests:read")

    def test_make_bundle_refresh_without_scope_keeps_previous_granted_scopes(self):
        # Refresh sin `scope` en la respuesta: el grant no cambió. No debe
        # sobrescribirse con los scopes "solicitados" si son más amplios que
        # los realmente concedidos antes.
        previous = {"refresh_token": "rt-old", "scopes": "sleep:read"}
        bundle = auth.make_bundle(
            {"access_token": "at2"}, scopes="sleep:read ppi_data:read", previous=previous, refresh=True
        )
        self.assertEqual(bundle["scopes"], "sleep:read")

    def test_make_bundle_exchange_with_previous_uses_requested_scopes(self):
        # Re-autorización (exchange) con bundle previo: si la respuesta omite
        # `scope`, RFC 6749 dice "idéntico a lo solicitado". Heredar los
        # scopes viejos dejaría el bundle inválido tras ampliar
        # POLAR_V4_SCOPES (bucle de re-auth sin salida).
        previous = {"refresh_token": "rt-old", "scopes": "sleep:read", "x_user_id": "u1"}
        bundle = auth.make_bundle(
            {"access_token": "at2", "refresh_token": "rt-new"},
            scopes="sleep:read ppi_data:read",
            previous=previous,
        )
        self.assertEqual(bundle["scopes"], "sleep:read ppi_data:read")
        # previous sigue sirviendo para preservar x_user_id.
        self.assertEqual(bundle["x_user_id"], "u1")

    def test_load_bundle_returns_expired_bundle(self):
        # Un access token expirado NO invalida el bundle (hay refresh token).
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "polar_tokens_v4.json"
            path.write_text(json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 10,
                "obtained_at": time.time() - 99999,
            }), encoding="utf-8")
            bundle = auth.load_bundle_v4(path)
        self.assertIsNotNone(bundle)
        self.assertTrue(auth.bundle_needs_refresh(bundle))

    def test_bundle_needs_refresh_respects_skew(self):
        fresh = {"access_token": "at", "expires_in": 43199, "obtained_at": time.time()}
        near_expiry = {"access_token": "at", "expires_in": 100, "obtained_at": time.time()}
        self.assertFalse(auth.bundle_needs_refresh(fresh))
        self.assertTrue(auth.bundle_needs_refresh(near_expiry, skew_s=120))

    def test_bundle_with_non_numeric_expiry_is_refreshable_not_valueerror(self):
        # Bundle corrupto (expires_in/obtained_at no numéricos): debe
        # clasificarse como refrescable, no lanzar ValueError hacia el flujo
        # de refresh o /api/status.
        self.assertTrue(auth.bundle_needs_refresh(
            {"access_token": "at", "expires_in": "abc", "obtained_at": time.time()}
        ))
        self.assertTrue(auth.bundle_needs_refresh(
            {"access_token": "at", "expires_in": 43199, "obtained_at": "corrupto"}
        ))

    def test_bundle_without_expiry_needs_refresh(self):
        # Bundle malformado/parcial sin expires_in: no se puede garantizar
        # que el access token siga vivo → refresh, nunca frescura implícita.
        self.assertTrue(auth.bundle_needs_refresh({"access_token": "at", "obtained_at": time.time()}))
        self.assertTrue(auth.bundle_needs_refresh({"access_token": "at", "expires_in": 0}))

    def test_scopes_match(self):
        bundle = {"scopes": "sleep:read nightly_recharge:read training_sessions:read"}
        self.assertTrue(auth.bundle_scopes_match(bundle, "sleep:read nightly_recharge:read"))
        self.assertFalse(auth.bundle_scopes_match(bundle, "sleep:read ppi_data:read"))
        # Bundle legado sin scopes registrados: no bloquea.
        self.assertTrue(auth.bundle_scopes_match({}, "sleep:read"))

    def test_redact_never_exposes_tokens(self):
        bundle = {"access_token": "at-secreto", "refresh_token": "rt-secreto", "expires_in": 43199,
                  "obtained_at": time.time(), "scopes": "sleep:read", "x_user_id": "u1"}
        safe = json.dumps(auth.redact(bundle))
        self.assertNotIn("at-secreto", safe)
        self.assertNotIn("rt-secreto", safe)
        self.assertIn("has_refresh_token", safe)


class GetValidAccessTokenTests(unittest.TestCase):
    def _write_bundle(self, path: Path, **overrides):
        bundle = {
            "access_token": "at-old",
            "refresh_token": "rt-old",
            "expires_in": 43199,
            "obtained_at": time.time(),
            "scopes": "sleep:read",
            "provider_version": "v4",
        }
        bundle.update(overrides)
        path.write_text(json.dumps(bundle), encoding="utf-8")
        return bundle

    def test_fresh_token_returned_without_refresh(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path)
            with patch.object(auth, "refresh_access_token_v4", side_effect=AssertionError("no debe refrescar")):
                token = auth.get_valid_access_token(path, client_id="cid", client_secret="sec", expected_scopes="sleep:read")
        self.assertEqual(token, "at-old")

    def test_expired_token_is_refreshed_and_rotated_atomically(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, obtained_at=time.time() - 99999)
            with patch.object(auth, "refresh_access_token_v4",
                              return_value={"access_token": "at-new", "refresh_token": "rt-new", "expires_in": 43199}):
                token = auth.get_valid_access_token(path, client_id="cid", client_secret="sec", expected_scopes="sleep:read")
            persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(token, "at-new")
        self.assertEqual(persisted["access_token"], "at-new")
        self.assertEqual(persisted["refresh_token"], "rt-new")
        self.assertEqual(persisted["provider_version"], "v4")

    def test_rotation_without_new_refresh_token_keeps_previous(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, obtained_at=time.time() - 99999)
            with patch.object(auth, "refresh_access_token_v4",
                              return_value={"access_token": "at-new", "expires_in": 43199}):
                auth.get_valid_access_token(path, client_id="cid", client_secret="sec", expected_scopes="sleep:read")
            persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["refresh_token"], "rt-old")

    def test_scopes_mismatch_requires_reauth(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, scopes="sleep:read")
            token = auth.get_valid_access_token(
                path, client_id="cid", client_secret="sec", expected_scopes="sleep:read ppi_data:read"
            )
        self.assertIsNone(token)

    def test_refresh_failure_returns_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, obtained_at=time.time() - 99999)
            with patch.object(auth, "refresh_access_token_v4", side_effect=auth.PolarAuthV4Error("boom")):
                token = auth.get_valid_access_token(path, client_id="cid", client_secret="sec", expected_scopes="sleep:read")
        self.assertIsNone(token)

    def test_refresh_serialized_via_lockfile(self):
        # Si el lockfile ya existe (otro proceso refrescando), no se quema el
        # refresh token: la llamada degrada a None sin hablar con la red.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, obtained_at=time.time() - 99999)
            lock_path = Path(str(path) + ".lock")
            lock_path.write_text(str(time.time()))
            try:
                # Timeout corto: sin esto el test esperaría los 30s reales
                # del deadline del lockfile.
                with patch.object(auth, "_FILE_LOCK_TIMEOUT_SEC", 0.3), \
                        patch.object(auth, "refresh_access_token_v4",
                                     side_effect=AssertionError("no debe llamar a refresh")):
                    token = auth.get_valid_access_token(
                        path, client_id="cid", client_secret="sec", expected_scopes="sleep:read"
                    )
            finally:
                lock_path.unlink(missing_ok=True)
        self.assertIsNone(token)

    def test_refresh_breaks_stale_lockfile(self):
        # Lock huérfano (>60s): se rompe y el refresh procede.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, obtained_at=time.time() - 99999)
            lock_path = Path(str(path) + ".lock")
            lock_path.write_text("stale")
            old = time.time() - 9999
            os.utime(lock_path, (old, old))
            with patch.object(auth, "refresh_access_token_v4",
                              return_value={"access_token": "at-new", "expires_in": 43199}):
                token = auth.get_valid_access_token(
                    path, client_id="cid", client_secret="sec", expected_scopes="sleep:read"
                )
        self.assertEqual(token, "at-new")

    def test_persist_authorized_bundle_saves_under_lock_and_preserves_x_user_id(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            self._write_bundle(path, x_user_id="u1")
            bundle = auth.persist_authorized_bundle(
                path, {"access_token": "at-new", "refresh_token": "rt-new", "expires_in": 43199},
                scopes="sleep:read",
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))
            # El lockfile se libera al terminar.
            self.assertFalse(Path(str(path) + ".lock").exists())
        self.assertEqual(persisted["access_token"], "at-new")
        self.assertEqual(persisted["x_user_id"], "u1")
        self.assertEqual(bundle["scopes"], "sleep:read")

    def test_persist_authorized_bundle_raises_if_lock_unobtainable(self):
        # Si el lock no se obtiene ni rompiendo huérfanos (patológico), el
        # exchange falla tipado en vez de escribir sin lock: escribir a
        # ciegas dejaría que un refresh en vuelo restaure credenciales
        # antiguas. El usuario reintenta /auth.
        from contextlib import contextmanager

        @contextmanager
        def fake_lock(_path, timeout=None):
            yield False

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            with patch.object(auth, "_file_lock", fake_lock):
                with self.assertRaises(auth.PolarAuthV4Error):
                    auth.persist_authorized_bundle(
                        path, {"access_token": "at-new", "expires_in": 43199}, scopes="sleep:read"
                    )
            self.assertFalse(path.exists())

    def test_persist_authorized_bundle_breaks_stale_lock_and_writes(self):
        # Un lock huérfano (refresh muerto) no debe bloquear el grant del
        # usuario: se rompe vía TTL y el exchange persiste bajo lock.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            lock_path = Path(str(path) + ".lock")
            lock_path.write_text("stale")
            old = time.time() - 9999
            os.utime(lock_path, (old, old))
            auth.persist_authorized_bundle(
                path, {"access_token": "at-new", "expires_in": 43199}, scopes="sleep:read"
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(lock_path.exists())
        self.assertEqual(persisted["access_token"], "at-new")

    def test_missing_bundle_returns_none(self):
        with TemporaryDirectory() as tmp:
            token = auth.get_valid_access_token(
                Path(tmp) / "missing.json", client_id="cid", client_secret="sec", expected_scopes="sleep:read"
            )
        self.assertIsNone(token)


if __name__ == "__main__":
    unittest.main()
