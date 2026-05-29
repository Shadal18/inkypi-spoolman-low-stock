from plugins.base_plugin.base_plugin import BasePlugin
import requests


def safe_float(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


class SpoolmanLowStock(BasePlugin):
    def generate_image(self, settings, device_config):
        title = (settings.get("title") or "").strip() or "Low Stock Filament"
        base_url = (settings.get("spoolman_url") or "").strip().rstrip("/")
        material_filter = (settings.get("materials") or "").strip()
        hide_empty = str(settings.get("hide_empty", "true")).lower() in ("true", "1", "yes", "on")
        max_items = int(settings.get("max_items", 5) or 5)
        low_threshold = safe_float(settings.get("low_threshold"), 250)
        critical_threshold = safe_float(settings.get("critical_threshold"), 100)

        if not base_url:
            raise RuntimeError("Spoolman URL is required.")

        api_url = f"{base_url}/api/v1/spool"

        try:
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            spools = response.json()
        except requests.exceptions.HTTPError as e:
            content = e.response.text if e.response is not None else "No response content"
            status_code = e.response.status_code if e.response is not None else "unknown"
            raise RuntimeError(f"HTTP error {status_code}: {content}") from e
        except requests.exceptions.Timeout as e:
            raise RuntimeError("Request timed out trying to fetch Spoolman data.") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network or connection error: {str(e)}") from e
        except ValueError as e:
            raise RuntimeError("Failed to parse Spoolman response as JSON.") from e

        allowed_materials = {
            part.strip().upper()
            for part in material_filter.split(",")
            if part.strip()
        }

        filtered = []
        for spool in spools:
            filament = spool.get("filament") or {}

            remaining_weight = safe_float(spool.get("remaining_weight"), 0)
            material = (filament.get("material") or "").strip().upper()

            if hide_empty and remaining_weight <= 0:
                continue

            if allowed_materials and material not in allowed_materials:
                continue

            if remaining_weight > low_threshold:
                continue

            vendor = (
                (filament.get("vendor") or {}).get("name")
                or filament.get("vendor_name")
                or "Unknown"
            )
            name = filament.get("name") or "Unnamed Filament"
            color_hex = filament.get("color_hex") or filament.get("multi_color_hexes") or ""
            location = spool.get("location") or ""
            used_weight = safe_float(spool.get("used_weight"), 0)

            status = "Critical" if remaining_weight <= critical_threshold else "Low"

            filtered.append({
                "id": spool.get("id"),
                "name": name,
                "vendor": vendor,
                "material": material or "Unknown",
                "remaining_weight": int(round(remaining_weight)),
                "used_weight": int(round(used_weight)),
                "location": location,
                "color_hex": color_hex,
                "status": status,
            })

        filtered.sort(key=lambda item: item["remaining_weight"])

        total_low = len(filtered)
        total_critical = sum(1 for item in filtered if item["status"] == "critical")
        items = filtered[:max_items]

        if not items:
            items = [{
                "id": "",
                "name": "No low-stock spools",
                "vendor": "",
                "material": "",
                "remaining_weight": 0,
                "used_weight": 0,
                "location": "",
                "color_hex": "",
                "status": "All Good",
            }]

        width, height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width

        return self.render_image(
            dimensions=(width, height),
            html_file="spoolman_low_stock.html",
            css_file="spoolman_low_stock.css",
            template_params={
                "title": title,
                "items": items,
                "total_low": total_low,
                "total_critical": total_critical,
                "low_threshold": int(round(low_threshold)),
                "critical_threshold": int(round(critical_threshold)),
                "plugin_settings": settings,
            }
        )

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["style_settings"] = True
        template_params["title"] = {
            "required": False,
            "description": "Header text",
            "example": "Low Stock Filament",
        }
        template_params["spoolman_url"] = {
            "required": True,
            "description": "Base URL for your Spoolman instance",
            "example": "http://spoolman.lan",
        }
        template_params["materials"] = {
            "required": False,
            "description": "Optional comma-separated material filter",
            "example": "PLA,PETG,ASA",
        }
        template_params["low_threshold"] = {
            "required": False,
            "description": "Low stock threshold in grams",
            "example": "250",
        }
        template_params["critical_threshold"] = {
            "required": False,
            "description": "Critical stock threshold in grams",
            "example": "100",
        }
        template_params["max_items"] = {
            "required": False,
            "description": "Maximum number of spools to show",
            "example": "5",
        }
        return template_params