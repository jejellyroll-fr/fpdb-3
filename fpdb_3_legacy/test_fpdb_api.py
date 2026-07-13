#!/usr/bin/env python3
from __future__ import annotations
"""
FPDB API Test Suite
===================

Script de test pour vérifier que l'API FPDB fonctionne correctement.

Usage:
    # L'API doit être démarrée avant de lancer les tests
    python run_fpdb_api.py &
    sleep 3
    python test_fpdb_api.py

    # Ou avec un host/port personnalisé
    python test_fpdb_api.py --host 127.0.0.1 --port 8000
"""

import argparse
import json
import sys
from typing import Dict, Any

try:
    import requests
except ImportError:
    print("❌ Le module 'requests' n'est pas installé.")
    print("   Installez-le avec: pip install requests")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output"""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class APITester:
    """Test FPDB API endpoints"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token = None
        self.tests_passed = 0
        self.tests_failed = 0

    def print_header(self, title: str):
        """Print section header"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{title.center(80)}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}\n")

    def print_test(self, name: str, method: str, endpoint: str):
        """Print test information"""
        print(f"{Colors.BLUE}🧪 Test:{Colors.RESET} {name}")
        print(f"   {Colors.YELLOW}{method}{Colors.RESET} {endpoint}")

    def print_success(self, message: str = "✅ Test réussi"):
        """Print success message"""
        print(f"   {Colors.GREEN}{message}{Colors.RESET}\n")
        self.tests_passed += 1

    def print_error(self, message: str):
        """Print error message"""
        print(f"   {Colors.RED}❌ {message}{Colors.RESET}\n")
        self.tests_failed += 1

    def print_response(self, response: requests.Response):
        """Print response details"""
        print(f"   Status: {response.status_code}")
        try:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
        except ValueError:
            print(f"   Response: {response.text[:200]}...")

    def test_health_check(self):
        """Test health check endpoint"""
        self.print_test("Health Check", "GET", "/health")
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    self.print_success("✅ API is healthy")
                else:
                    self.print_error("Health check returned unexpected status")
            else:
                self.print_error(f"Health check failed with status {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.print_error("Cannot connect to API - Is the server running?")
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_root_endpoint(self):
        """Test root endpoint"""
        self.print_test("Root Endpoint", "GET", "/")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "name" in data and "version" in data:
                    self.print_success(f"✅ API {data['name']} v{data['version']}")
                else:
                    self.print_error("Root endpoint returned unexpected data")
            else:
                self.print_error(f"Root endpoint failed with status {response.status_code}")
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_openapi_docs(self):
        """Test OpenAPI documentation"""
        self.print_test("OpenAPI Docs", "GET", "/docs")
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=5)
            if response.status_code == 200:
                self.print_success("✅ Documentation Swagger accessible")
            else:
                self.print_error(f"Docs failed with status {response.status_code}")
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_graphql_endpoint(self):
        """Test GraphQL endpoint"""
        self.print_test("GraphQL Introspection", "POST", "/graphql")
        query = {"query": "{ __schema { queryType { name } } }"}
        try:
            response = requests.post(
                f"{self.base_url}/graphql",
                json=query,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    self.print_success("✅ GraphQL endpoint functional")
                else:
                    self.print_error("GraphQL returned unexpected response")
            else:
                self.print_error(f"GraphQL failed with status {response.status_code}")
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_register_user(self):
        """Test user registration"""
        self.print_test("User Registration", "POST", "/api/v1/auth/register")
        payload = {
            "username": f"testuser_{id(self)}",
            "email": f"test_{id(self)}@example.com",
            "password": "TestPassword123!",
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/auth/register",
                json=payload,
                timeout=5,
            )
            if response.status_code in [200, 201]:
                self.print_success("✅ User registered successfully")
                return True
            elif response.status_code == 400:
                # User might already exist, try to login instead
                self.print_success("✅ User already exists (expected)")
                return True
            else:
                self.print_error(f"Registration failed with status {response.status_code}")
                self.print_response(response)
                return False
        except Exception as e:
            self.print_error(f"Exception: {e}")
            return False

    def test_login_user(self):
        """Test user login"""
        self.print_test("User Login", "POST", "/api/v1/auth/login")
        payload = {
            "username": f"testuser_{id(self)}",
            "password": "TestPassword123!",
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/auth/login",
                data=payload,  # OAuth2 uses form data
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.token = data["access_token"]
                    self.print_success(f"✅ Login successful - Token: {self.token[:20]}...")
                    return True
                else:
                    self.print_error("Login response missing access_token")
                    return False
            else:
                self.print_error(f"Login failed with status {response.status_code}")
                self.print_response(response)
                return False
        except Exception as e:
            self.print_error(f"Exception: {e}")
            return False

    def test_get_players(self):
        """Test get players endpoint"""
        self.print_test("Get Players", "GET", "/api/v1/players")
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = requests.get(
                f"{self.base_url}/api/v1/players",
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                # API returns PagedResponse with "items" field
                if "items" in data:
                    count = len(data["items"])
                    total = data.get("total", count)
                    self.print_success(f"✅ Found {count} player(s) (total: {total})")
                else:
                    self.print_error("Response missing 'items' field")
            elif response.status_code == 401:
                self.print_error("Unauthorized - Authentication required")
            else:
                self.print_error(f"Get players failed with status {response.status_code}")
                self.print_response(response)
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_get_tournaments(self):
        """Test get tournaments endpoint"""
        self.print_test("Get Tournaments", "GET", "/api/v1/tournaments")
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = requests.get(
                f"{self.base_url}/api/v1/tournaments",
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                if "tournaments" in data:
                    count = len(data["tournaments"])
                    self.print_success(f"✅ Found {count} tournament(s)")
                else:
                    self.print_error("Response missing 'tournaments' field")
            elif response.status_code == 401:
                self.print_error("Unauthorized - Authentication required")
            else:
                self.print_error(f"Get tournaments failed with status {response.status_code}")
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_get_hud_presets(self):
        """Test get HUD presets endpoint"""
        self.print_test("Get HUD Presets", "GET", "/api/v1/hud/presets")
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = requests.get(
                f"{self.base_url}/api/v1/hud/presets",
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                # API returns list of HUDPresetListItemDTO
                if isinstance(data, list):
                    count = len(data)
                    self.print_success(f"✅ Found {count} HUD preset(s)")
                else:
                    self.print_error("Expected list response")
            elif response.status_code == 401:
                self.print_error("Unauthorized - Authentication required")
            else:
                self.print_error(f"Get HUD presets failed with status {response.status_code}")
                self.print_response(response)  # Show error details
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def test_websocket_stats(self):
        """Test WebSocket stats endpoint"""
        self.print_test("WebSocket Stats", "GET", "/ws/stats")
        try:
            response = requests.get(f"{self.base_url}/ws/stats", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "active_connections" in data:
                    count = data["active_connections"]
                    self.print_success(f"✅ WebSocket active connections: {count}")
                else:
                    self.print_error("Response missing 'active_connections' field")
            else:
                self.print_error(f"WebSocket stats failed with status {response.status_code}")
        except Exception as e:
            self.print_error(f"Exception: {e}")

    def print_summary(self):
        """Print test summary"""
        self.print_header("Test Summary")
        total = self.tests_passed + self.tests_failed
        print(f"{Colors.BOLD}Total tests:{Colors.RESET} {total}")
        print(f"{Colors.GREEN}Passed:{Colors.RESET} {self.tests_passed}")
        print(f"{Colors.RED}Failed:{Colors.RESET} {self.tests_failed}")

        if self.tests_failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ All tests passed!{Colors.RESET}\n")
            return 0
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ Some tests failed{Colors.RESET}\n")
            return 1

    def run_all_tests(self):
        """Run all API tests"""
        self.print_header("FPDB API Test Suite")
        print(f"Testing API at: {Colors.BOLD}{self.base_url}{Colors.RESET}\n")

        # Core endpoints
        self.test_health_check()
        self.test_root_endpoint()
        self.test_openapi_docs()
        self.test_graphql_endpoint()

        # Authentication flow
        if self.test_register_user():
            if self.test_login_user():
                # Authenticated endpoints
                self.test_get_players()
                self.test_get_tournaments()
                self.test_get_hud_presets()

        # WebSocket stats
        self.test_websocket_stats()

        # Print summary
        return self.print_summary()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Test FPDB API endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="API host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API port (default: 8000)",
    )
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    tester = APITester(base_url)

    try:
        exit_code = tester.run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
