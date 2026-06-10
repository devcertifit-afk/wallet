import json
import io
import zipfile
import hashlib
from decimal import Decimal
from django.conf import settings
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
import jwt
import time

# A valid 1x1 transparent PNG to serve as placeholder image
PLACEHOLDER_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

class ApplePassGenerator:
    def __init__(self, pass_instance):
        self.instance = pass_instance
        self.template = pass_instance.template
        self.company = self.template.company

    def build_pass_json(self):
        """Construct the pass.json payload."""
        serial_str = str(self.instance.serial_number)
        
        # Determine the pass structure name based on the PassTemplate type
        pass_structure = {}
        
        pass_data = self.instance.pass_data or {}
        
        header_fields = []
        primary_fields = []
        secondary_fields = []
        auxiliary_fields = []
        
        pt = self.template.pass_type
        if pt == 'LOYALTY':
            header_fields = [{"key": "balance", "label": "POINTS", "value": int(self.instance.balance)}]
            primary_fields = [{"key": "customer", "label": "CUSTOMER", "value": self.instance.customer_name}]
            secondary_fields = [{"key": "email", "label": "EMAIL", "value": self.instance.customer_email}]
        elif pt == 'GIFT_CARD':
            header_fields = [{"key": "balance", "label": "BALANCE", "value": f"€{self.instance.balance:.2f}"}]
            primary_fields = [{"key": "customer", "label": "CUSTOMER", "value": self.instance.customer_name}]
            secondary_fields = [{"key": "email", "label": "EMAIL", "value": self.instance.customer_email}]
        elif pt == 'EVENT_TICKET':
            header_fields = [{"key": "event_date", "label": "DATE", "value": pass_data.get('event_date') or "TBD"}]
            primary_fields = [{"key": "event_name", "label": "EVENT", "value": pass_data.get('event_name') or self.template.title}]
            secondary_fields = [
                {"key": "venue", "label": "VENUE", "value": pass_data.get('venue') or "TBD"},
                {"key": "seat", "label": "SEAT", "value": pass_data.get('seat') or "General"}
            ]
            auxiliary_fields = [{"key": "customer", "label": "ATTENDEE", "value": self.instance.customer_name}]
        elif pt == 'BOARDING_PASS':
            header_fields = [{"key": "flight", "label": "FLIGHT", "value": pass_data.get('flight_number') or "TBD"}]
            primary_fields = [
                {"key": "origin", "label": "FROM", "value": pass_data.get('origin') or "TBD"},
                {"key": "destination", "label": "TO", "value": pass_data.get('destination') or "TBD"}
            ]
            secondary_fields = [
                {"key": "dep_time", "label": "DEPARTS", "value": pass_data.get('departure_time') or "TBD"},
                {"key": "seat", "label": "SEAT", "value": pass_data.get('seat') or "TBD"}
            ]
            auxiliary_fields = [{"key": "customer", "label": "PASSENGER", "value": self.instance.customer_name}]
        elif pt == 'COUPON':
            header_fields = [{"key": "expires", "label": "EXPIRES", "value": pass_data.get('expires_at') or "TBD"}]
            primary_fields = [{"key": "discount", "label": "OFFER", "value": pass_data.get('discount_value') or self.template.title}]
            secondary_fields = [{"key": "code", "label": "PROMO CODE", "value": pass_data.get('coupon_code') or "None"}]
            auxiliary_fields = [{"key": "customer", "label": "CUSTOMER", "value": self.instance.customer_name}]
        elif pt == 'MEMBERSHIP':
            header_fields = [{"key": "tier", "label": "TIER", "value": pass_data.get('membership_tier') or "Standard"}]
            primary_fields = [{"key": "customer", "label": "MEMBER", "value": self.instance.customer_name}]
            secondary_fields = [
                {"key": "member_id", "label": "MEMBER ID", "value": pass_data.get('membership_id') or str(self.instance.serial_number)[:8]},
                {"key": "expires", "label": "EXPIRES", "value": pass_data.get('expires_at') or "TBD"}
            ]
        else: # GENERIC
            header_fields = [{"key": "title", "label": "CARD", "value": self.template.title}]
            primary_fields = [{"key": "customer", "label": "HOLDER", "value": self.instance.customer_name}]
            secondary_fields = []
            if pass_data.get('custom_label_1'):
                secondary_fields.append({"key": "custom_1", "label": pass_data.get('custom_label_1'), "value": pass_data.get('custom_value_1')})
            if pass_data.get('custom_label_2'):
                secondary_fields.append({"key": "custom_2", "label": pass_data.get('custom_label_2'), "value": pass_data.get('custom_value_2')})

        pass_structure = {
            "headerFields": header_fields,
            "primaryFields": primary_fields,
            "secondaryFields": secondary_fields
        }
        if auxiliary_fields:
            pass_structure["auxiliaryFields"] = auxiliary_fields

        # Map Django pass type to native Apple pass structure key
        apple_pass_type = "generic"
        if self.template.pass_type in ['LOYALTY', 'GIFT_CARD']:
            apple_pass_type = "storeCard"
        elif self.template.pass_type == 'MEMBERSHIP':
            apple_pass_type = "generic"
        elif self.template.pass_type == 'COUPON':
            apple_pass_type = "coupon"
        elif self.template.pass_type == 'EVENT_TICKET':
            apple_pass_type = "eventTicket"
        elif self.template.pass_type == 'BOARDING_PASS':
            apple_pass_type = "boardingPass"
            pass_structure["transitType"] = "PKTransitTypeGeneric"

        # Build final pass dictionary
        pass_dict = {
            "formatVersion": 1,
            "passTypeIdentifier": self.template.apple_pass_type_id or "pass.com.flow.generic",
            "serialNumber": serial_str,
            "teamIdentifier": getattr(settings, 'APPLE_TEAM_IDENTIFIER', '12345ABCDE'),
            "organizationName": self.company.name,
            "description": self.template.description or f"{self.template.title} Pass",
            "logoText": self.template.title,
            "foregroundColor": self.template.foreground_color,
            "backgroundColor": self.template.background_color,
            "labelColor": self.template.label_color,
            "barcodes": [
                {
                    "message": serial_str,
                    "format": "PKBarcodeFormatQR",
                    "messageEncoding": "iso-8859-1",
                    "altText": serial_str[:8]
                }
            ],
            "userInfo": {
                "sku": self.template.sku or "",
                "metadata": self.template.custom_metadata or {}
            },
            # Dynamic mapping for pass structure style
            apple_pass_type: pass_structure
        }
        
        return pass_dict

    def generate_manifest(self, files):
        """Generate manifest.json from dictionary of file paths and bytes."""
        manifest = {}
        for filepath, data in files.items():
            manifest[filepath] = hashlib.sha1(data).hexdigest()
        return json.dumps(manifest).encode('utf-8')

    def sign_manifest(self, manifest_data):
        """Sign manifest.json using PKCS#7. Fall back to mock signature if certificates are missing."""
        cert_pem = getattr(settings, 'APPLE_PASS_CERT', None)
        key_pem = getattr(settings, 'APPLE_PASS_KEY', None)
        wwdr_pem = getattr(settings, 'APPLE_WWDR_CERT', None)

        if not all([cert_pem, key_pem, wwdr_pem]):
            raise ValueError(
                "Missing Apple Certificates. Please ensure APPLE_PASS_CERT, "
                "APPLE_PASS_KEY, and APPLE_WWDR_CERT are set in GCP Secret Manager or .env"
            )

        try:
            # Load keys and certificates
            key = load_pem_private_key(key_pem.encode('utf-8'), password=None)
            cert = load_pem_x509_certificate(cert_pem.encode('utf-8'))
            wwdr_cert = load_pem_x509_certificate(wwdr_pem.encode('utf-8'))

            # Configure PKCS#7 options
            options = [pkcs7.PKCS7Options.DetachedSignature]
            
            # Sign manifest using SHA-1 (Apple Wallet standard)
            signature = pkcs7.PKCS7SignatureBuilder().set_data(
                manifest_data
            ).add_signer(
                cert, key, hashes.SHA1()
            ).add_certificate(
                wwdr_cert
            ).sign(
                serialization.Encoding.DER, options
            )
            return signature
        except Exception as e:
            raise RuntimeError(f"Failed to sign Apple Pass manifest: {str(e)}")

    def generate_pkpass(self):
        """Generate the complete signed .pkpass binary package."""
        files = {
            'pass.json': json.dumps(self.build_pass_json(), indent=2).encode('utf-8'),
            'icon.png': PLACEHOLDER_PNG,
            'icon@2x.png': PLACEHOLDER_PNG,
            'logo.png': PLACEHOLDER_PNG,
            'logo@2x.png': PLACEHOLDER_PNG,
        }

        # Handle custom uploaded logo if present in the template
        if self.template.logo:
            try:
                self.template.logo.open('rb')
                files['logo.png'] = self.template.logo.read()
                self.template.logo.close()
            except Exception:
                pass # Fall back to placeholder if file cannot be read

        # Generate manifest
        manifest_data = self.generate_manifest(files)
        files['manifest.json'] = manifest_data

        # Sign manifest
        signature_data = self.sign_manifest(manifest_data)
        files['signature'] = signature_data

        # Compress into ZIP/pkpass format in-memory
        pkpass_buffer = io.BytesIO()
        with zipfile.ZipFile(pkpass_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filepath, data in files.items():
                zip_file.writestr(filepath, data)
        
        return pkpass_buffer.getvalue()


class GoogleWalletGenerator:
    def __init__(self, pass_instance):
        self.instance = pass_instance
        self.template = pass_instance.template
        self.company = self.template.company

    def build_object_payload(self):
        """Construct the Google Wallet Object payload (LoyaltyObject / GiftCardObject / GenericObject)."""
        issuer_id = getattr(settings, 'GOOGLE_WALLET_ISSUER_ID', '3388000000000000000')
        class_id = self.template.google_class_id or f"{issuer_id}.{self.template.id}"
        object_id = self.instance.google_object_id or f"{issuer_id}.{self.instance.serial_number}"

        # Standard Google Wallet object dictionary
        payload = {
            "id": object_id,
            "classId": class_id,
            "state": "ACTIVE",
            "barcode": {
                "type": "QR_CODE",
                "value": str(self.instance.serial_number),
                "alternateText": str(self.instance.serial_number)[:8]
            },
            "customData": {
                "sku": self.template.sku or "",
                "metadata": self.template.custom_metadata or {}
            },
            "heroImage": {
                "sourceUri": {
                    "uri": "https://storage.googleapis.com/wallet-assets-devcertifit/hero_placeholder.png"
                }
            }
        }

        pass_data = self.instance.pass_data or {}
        
        # Set specific fields depending on type
        if self.template.pass_type == 'LOYALTY':
            payload.update({
                "loyaltyPoints": {
                    "balance": {
                        "string": f"{int(self.instance.balance)} pts"
                    },
                    "label": "Points Balance"
                },
                "accountName": self.instance.customer_name,
                "accountId": self.instance.customer_email
            })
        elif self.template.pass_type == 'GIFT_CARD':
            payload.update({
                "balance": {
                    "micros": int(self.instance.balance * 1000000),
                    "currencyCode": "EUR"
                },
                "cardNumber": str(self.instance.serial_number)[:16],
                "cardholderName": self.instance.customer_name
            })
        elif self.template.pass_type == 'EVENT_TICKET':
            payload.update({
                "eventName": pass_data.get('event_name') or self.template.title,
                "ticketHolderName": self.instance.customer_name,
                "venue": {
                    "name": pass_data.get('venue') or "TBD"
                },
                "dateTime": {
                    "start": pass_data.get('event_date') or ""
                },
                "seatInfo": {
                    "seat": pass_data.get('seat') or "General Admission"
                }
            })
        elif self.template.pass_type == 'COUPON':
            payload.update({
                "title": pass_data.get('discount_value') or self.template.title,
                "redemptionCode": pass_data.get('coupon_code') or "None",
                "validTimeInterval": {
                    "end": pass_data.get('expires_at') or ""
                }
            })
        elif self.template.pass_type == 'BOARDING_PASS':
            payload.update({
                "flightHeader": {
                    "carrier": {
                        "carrierIataCode": self.template.default_data.get('default_carrier') or "BT"
                    },
                    "flightNumber": pass_data.get('flight_number') or "TBD"
                },
                "origin": {
                    "airportIataCode": pass_data.get('origin') or "TBD"
                },
                "destination": {
                    "airportIataCode": pass_data.get('destination') or "TBD"
                },
                "passengerName": self.instance.customer_name,
                "boardingAndDepartureUtcTimes": {
                    "departureUtcTime": pass_data.get('departure_time') or ""
                }
            })
        elif self.template.pass_type == 'MEMBERSHIP':
            payload.update({
                "membershipDetails": {
                    "membershipNumber": pass_data.get('membership_id') or str(self.instance.serial_number)[:8],
                    "programName": self.template.title,
                    "membershipLevel": pass_data.get('membership_tier') or "Standard"
                },
                "cardholderName": self.instance.customer_name
            })
        else: # GENERIC
            payload.update({
                "cardholderName": self.instance.customer_name,
                "cardNumber": str(self.instance.serial_number)[:16]
            })

        return payload

    def generate_save_url(self):
        """Generate the Save to Google Wallet JWT link."""
        private_key = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_KEY', None)
        sa_email = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_EMAIL', None)

        object_payload = self.build_object_payload()
        pass_type_key = "genericObjects"
        if self.template.pass_type == 'LOYALTY':
            pass_type_key = "loyaltyObjects"
        elif self.template.pass_type == 'GIFT_CARD':
            pass_type_key = "giftCardObjects"
        elif self.template.pass_type == 'COUPON':
            pass_type_key = "offerObjects"
        elif self.template.pass_type == 'EVENT_TICKET':
            pass_type_key = "eventTicketObjects"
        elif self.template.pass_type == 'BOARDING_PASS':
            pass_type_key = "transitObjects"

        # Construct JWT payload
        claims = {
            "iss": sa_email or "wallet-sa@wallet-devcertifit.iam.gserviceaccount.com",
            "aud": "google",
            "typ": "savetowallet",
            "iat": int(time.time()),
            "origins": [],
            "payload": {
                pass_type_key: [object_payload]
            }
        }

        if not private_key:
            raise ValueError(
                "Missing Google Service Account Key. Please ensure "
                "GOOGLE_SERVICE_ACCOUNT_KEY is set in GCP Secret Manager or .env"
            )

        try:
            # Sign with RS256 service account private key
            token = jwt.encode(claims, private_key, algorithm="RS256")
            return f"https://pay.google.com/gp/v/save/{token}"
        except Exception as e:
            raise RuntimeError(f"Failed to sign Google Wallet JWT: {str(e)}")
