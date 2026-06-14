import io
import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from groups.models import Group
from expenses.models import Expense
from settlements.models import Settlement
from .models import ImportBatch, ImportAnomaly
from .parser import parse_csv
from .pipeline import run_import


User = get_user_model()


class CSVParserTests(TestCase):
    """
    Tests for the CSV parser module.

    Why: Verifies that CSV strings are correctly converted to dictionaries,
    and 1-based row indices are preserved for traceability.
    """

    def test_parse_csv_generic(self):
        """
        Why: Assures parser dynamically reads headers and attaches _row_index correctly.
        """
        csv_data = (
            "date,description,amount,currency\n"
            "2026-06-01,Lunch,120.00,INR\n"
            "2026-06-02,Cab,15.50,USD\n"
        )
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        rows = parse_csv(file_obj)

        self.assertEqual(len(rows), 2)
        # First data row is line 2 of the file (header is line 1)
        self.assertEqual(rows[0]['_row_index'], 2)
        self.assertEqual(rows[0]['description'], 'Lunch')
        self.assertEqual(rows[0]['amount'], '120.00')

        self.assertEqual(rows[1]['_row_index'], 3)
        self.assertEqual(rows[1]['description'], 'Cab')
        self.assertEqual(rows[1]['amount'], '15.50')


class AnomalyDetectorTests(TestCase):
    """
    Tests for the example anomaly detectors.

    Why: Verifies validation logic for DuplicateRowDetector and NegativeAmountDetector
    in isolation.
    """

    def test_duplicate_row_detector(self):
        """
        Why: Assures duplicate rows are flagged and matched back to their first occurrence.
        """
        from .detectors.example_detectors import DuplicateRowDetector
        rows = [
            {'_row_index': 2, 'date': '2026-06-01', 'desc': 'Coffee', 'cost': '10.00'},
            {'_row_index': 3, 'date': '2026-06-02', 'desc': 'Lunch', 'cost': '25.00'},
            {'_row_index': 4, 'date': '2026-06-01', 'desc': 'Coffee', 'cost': '10.00'},  # Duplicate of line 2
        ]
        detector = DuplicateRowDetector()
        anomalies = detector.detect(rows)

        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]['row_reference'], 'row 4')
        self.assertIn("duplicate of row 2", anomalies[0]['description'])
        self.assertIn("Skip row", anomalies[0]['suggested_action'])

    def test_negative_amount_detector(self):
        """
        Why: Assures negative quantities in amount-like columns are flagged.
        """
        from .detectors.example_detectors import NegativeAmountDetector
        rows = [
            {'_row_index': 2, 'date': '2026-06-01', 'amount': '50.00'},
            {'_row_index': 3, 'date': '2026-06-02', 'total_cost': '-15.00'},  # Negative
            {'_row_index': 4, 'date': '2026-06-03', 'price': '10.00'},
        ]
        detector = NegativeAmountDetector()
        anomalies = detector.detect(rows)

        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]['row_reference'], 'row 3')
        self.assertIn("Negative quantity '-15.00' found in amount column 'total_cost'", anomalies[0]['description'])


class ImportPipelineTests(TestCase):
    """
    Integration tests for the full import pipeline logic.

    Why: Validates that run_import correctly parses files, scans all detectors,
    and populates database tables within transaction limits.
    """

    def setUp(self):
        """
        Why: Setup user and group context.
        """
        self.user = User.objects.create_user(
            email="importer@example.com", name="Importer User", password="password123"
        )
        self.group = Group.objects.create(name="Import Trip", created_by=self.user)

    def test_pipeline_saves_batch_and_anomalies(self):
        """
        Why: Runs import on a file containing both a duplicate and a negative amount
        and confirms DB entries match expectations.
        """
        csv_content = (
            "date,description,charge_amount\n"
            "2026-06-01,Groceries,-50.00\n"  # Negative
            "2026-06-02,Train Ticket,100.00\n"
            "2026-06-02,Train Ticket,100.00\n"  # Duplicate of row 3
        )
        csv_file = SimpleUploadedFile("transactions.csv", csv_content.encode('utf-8'), content_type="text/csv")

        # Run pipeline
        batch = run_import(csv_file, self.group, self.user)

        # Confirm batch created
        self.assertEqual(ImportBatch.objects.count(), 1)
        self.assertEqual(batch.status, 'PENDING_REVIEW')
        self.assertEqual(batch.group, self.group)
        self.assertEqual(batch.uploaded_by, self.user)

        # Confirm anomalies created
        anomalies = ImportAnomaly.objects.filter(import_batch=batch)
        self.assertTrue(anomalies.count() >= 2)

        # Check negative amount anomaly
        neg_anomaly = anomalies.filter(anomaly_type='NEGATIVE_AMOUNT').first()
        self.assertIsNotNone(neg_anomaly)
        self.assertEqual(neg_anomaly.row_reference, 'row 2')
        self.assertEqual(neg_anomaly.status, 'PENDING')

        # Check duplicate anomaly
        dup_anomaly = anomalies.filter(anomaly_type='DUPLICATE_EXPENSE').first()
        self.assertIsNotNone(dup_anomaly)
        self.assertIn(dup_anomaly.row_reference, ['row 3', 'row 4'])
        self.assertEqual(dup_anomaly.status, 'PENDING')




class ImportViewsTests(TestCase):
    """
    Integration tests for import views and the review form page.

    Why: Validates HTTP responses, redirects, and decision submissions.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="meera@example.com", name="Meera Gate", password="password123"
        )
        self.group = Group.objects.create(name="Meera Group", created_by=self.user)
        self.client.login(username=self.user.email, password="password123")

    def test_upload_view_get(self):
        """
        Why: Upload view page renders.
        """
        url = reverse('import_upload', kwargs={'group_id': self.group.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import Expenses")

    def test_upload_view_post_creates_batch(self):
        """
        Why: Posting a CSV file creates a batch and redirects to the review page.
        """
        csv_content = "date,desc,amount\n2026-06-01,Cab,-10.00\n"
        csv_file = SimpleUploadedFile("data.csv", csv_content.encode('utf-8'), content_type="text/csv")
        url = reverse('import_upload', kwargs={'group_id': self.group.pk})

        response = self.client.post(url, {'csv_file': csv_file})
        self.assertEqual(response.status_code, 302)
        
        batch = ImportBatch.objects.first()
        self.assertIsNotNone(batch)
        self.assertRedirects(response, reverse('import_review', kwargs={'batch_id': batch.id}))

    def test_review_view_saves_decisions(self):
        """
        Why: Submitting Meera's approval gate updates anomaly resolutions.
        """
        from groups.models import GroupMembership
        from django.core.files.base import ContentFile
        
        batch = ImportBatch.objects.create(uploaded_by=self.user, group=self.group)
        
        # Attach dummy raw CSV file and group membership to satisfy apply_import constraints
        csv_content = "date,description,paid_by,amount,currency,split_type\n2026-06-01,Cab,meera@example.com,-10.00,INR,equal\n"
        batch.raw_file.save("data.csv", ContentFile(csv_content.encode('utf-8')))
        GroupMembership.objects.create(group=self.group, user=self.user, joined_at=datetime.date(2026, 1, 1))

        anomaly = ImportAnomaly.objects.create(
            import_batch=batch,
            row_reference="row 2",
            anomaly_type="NEGATIVE_AMOUNT",
            description="Neg",
            raw_row_data={'amount': '-10.00'},
            suggested_action="Abs",
            status="PENDING"
        )

        url = reverse('import_review', kwargs={'batch_id': batch.id})
        
        # Post decision: Approve
        data = {
            f"status_{anomaly.id}": "APPROVED",
            f"final_action_{anomaly.id}": "Abs applied"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # Verify database update
        anomaly.refresh_from_db()
        self.assertEqual(anomaly.status, 'APPROVED')
        self.assertEqual(anomaly.final_action, 'Abs applied')
        
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'APPROVED')



class CSVImportE2EIntegrationTests(TestCase):
    """
    Comprehensive End-to-End integration tests for the CSV Import pipeline.

    Why: Validates that CSV Upload, Detection, Review, Approval, Apply,
    Expense Creation, Settlement Creation, Balance Recalculation, and Reports
    operate correctly together and preserve financial data integrity.
    """

    def setUp(self):
        # 1. Setup users
        self.aisha = User.objects.create_user(email="aisha@example.com", name="Aisha", password="pass")
        self.rohan = User.objects.create_user(email="rohan@example.com", name="Rohan", password="pass")
        self.priya = User.objects.create_user(email="priya@example.com", name="Priya", password="pass")
        self.meera = User.objects.create_user(email="meera@example.com", name="Meera", password="pass")
        self.dev = User.objects.create_user(email="dev@example.com", name="Dev", password="pass")
        self.sam = User.objects.create_user(email="sam@example.com", name="Sam", password="pass")
        
        self.group = Group.objects.create(name="E2E Import Group", created_by=self.aisha)
        
        # 2. Setup memberships
        # Aisha, Rohan, Priya join on Jan 1
        from groups.models import GroupMembership
        GroupMembership.objects.create(group=self.group, user=self.aisha, joined_at=datetime.date(2026, 1, 1))
        GroupMembership.objects.create(group=self.group, user=self.rohan, joined_at=datetime.date(2026, 1, 1))
        GroupMembership.objects.create(group=self.group, user=self.priya, joined_at=datetime.date(2026, 1, 1))
        
        # Meera joins on Jan 1, leaves on March 31
        GroupMembership.objects.create(
            group=self.group, user=self.meera, joined_at=datetime.date(2026, 1, 1), left_at=datetime.date(2026, 3, 31)
        )
        # Dev joins on Feb 1, leaves on March 15
        GroupMembership.objects.create(
            group=self.group, user=self.dev, joined_at=datetime.date(2026, 2, 1), left_at=datetime.date(2026, 3, 15)
        )
        # Sam joins on April 1
        GroupMembership.objects.create(group=self.group, user=self.sam, joined_at=datetime.date(2026, 4, 1))

        # 3. Setup FXRates
        from core.models import FXRate
        FXRate.objects.create(from_currency='USD', to_currency='INR', rate=Decimal('80.00'), effective_date=datetime.date(2026, 3, 9))
        FXRate.objects.create(from_currency='USD', to_currency='INR', rate=Decimal('80.00'), effective_date=datetime.date(2026, 3, 10))
        FXRate.objects.create(from_currency='USD', to_currency='INR', rate=Decimal('80.00'), effective_date=datetime.date(2026, 3, 11))
        FXRate.objects.create(from_currency='USD', to_currency='INR', rate=Decimal('80.00'), effective_date=datetime.date(2026, 3, 12))

        self.client.login(username=self.aisha.email, password="pass")

    def test_full_e2e_import_flow(self):
        # 1. Prepare CSV data covering multiple anomaly situations
        csv_content = (
            "date,description,paid_by,amount,currency,split_type,split_with,split_details,notes\n"
            # Row 2: Normal Expense
            "01-02-2026,Groceries,Priya,2000,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
            # Row 3: Duplicate of Row 2
            "01-02-2026,Groceries,Priya,2000,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
            # Row 4: Negative Amount (Refund)
            "12-03-2026,Parasailing refund,Dev,-30,USD,equal,Aisha;Rohan;Priya;Dev,,\n"
            # Row 5: Missing Currency
            "15-03-2026,Cab to hotel,Priya,1000,,equal,Aisha;Rohan;Priya,,\n"
            # Row 6: Unsupported Currency
            "16-03-2026,Souvenirs,Rohan,50,EUR,equal,Aisha;Rohan,,\n"
            # Row 7: Zero Amount
            "22-03-2026,Free tickets,Priya,0,INR,equal,Aisha;Rohan,,\n"
            # Row 8: Missing Payer
            "22-02-2026,House cleaning supplies,,780,INR,equal,Aisha;Rohan,,\n"
            # Row 9: Settlement misclassification
            "25-02-2026,Rohan paid Aisha back,Rohan,5000,INR,,Aisha,,This is repayment\n"
            # Row 10: Invalid date
            "Mar-14,Airport cab,Rohan,1100,INR,equal,Aisha;Rohan,,\n"
            # Row 11: Ambiguous date
            "04-05-2026,Deep cleaning,Rohan,2500,INR,equal,Aisha;Rohan,,\n"
            # Row 12: Expense outside membership window (Meera left on March 31)
            "02-04-2026,Post-departure lunch,Priya,2640,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
            # Row 13: Unknown user (Kabir is not registered)
            "11-03-2026,Parasailing,Dev,150,USD,equal,Aisha;Rohan;Dev;Kabir,,\n"
            # Row 14: Invalid split percentage sum
            "28-02-2026,Pizza Friday,Aisha,1440,INR,percentage,Aisha;Rohan,Aisha 30%; Rohan 30%,\n"
            # Row 15: Missing required field (amount is blank)
            "20-02-2026,Dinner,,INR,equal,Aisha;Rohan,,\n"
            # Row 16: Conflicting duplicate (same date/desc/payer as row 2, different amount)
            "01-02-2026,Groceries,Priya,3000,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
            # Row 17: Split type mismatch (equal split declared, but unequal details given)
            "18-04-2026,Furniture,Aisha,12000,INR,equal,Aisha;Rohan,Aisha 1000; Rohan 2000,\n"
            # Row 18: Membership change event note
            "08-04-2026,Sam deposit share,Sam,15000,INR,equal,Aisha,,Sam moving in!\n"
        )
        
        csv_file = SimpleUploadedFile("expenses.csv", csv_content.encode('utf-8'), content_type="text/csv")
        
        # 2. Post the file upload
        upload_url = reverse('import_upload', kwargs={'group_id': self.group.id})
        response = self.client.post(upload_url, {'csv_file': csv_file})
        self.assertEqual(response.status_code, 302)
        
        batch = ImportBatch.objects.first()
        self.assertIsNotNone(batch)
        self.assertEqual(batch.status, 'PENDING_REVIEW')
        
        # Verify that anomalies were detected
        anomalies = list(batch.anomalies.all())
        self.assertTrue(len(anomalies) > 0)
        
        # 3. Post anomaly decisions to resolve the batch
        # We will approve/modify valid rows, and reject invalid/corrupted ones
        review_url = reverse('import_review', kwargs={'batch_id': batch.id})
        post_data = {}
        
        for anom in anomalies:
            row_ref = anom.row_reference
            
            # Rejections:
            if row_ref in ['row 3', 'row 6', 'row 7', 'row 13', 'row 14', 'row 15', 'row 16', 'row 17']:
                post_data[f"status_{anom.id}"] = "REJECTED"
                post_data[f"final_action_{anom.id}"] = "Skip bad data"
            
            # Modifications / Approvals:
            elif row_ref == 'row 5':  # Missing currency
                post_data[f"status_{anom.id}"] = "MODIFIED"
                post_data[f"final_action_{anom.id}"] = "Set currency to INR"
            elif row_ref == 'row 8':  # Missing payer
                post_data[f"status_{anom.id}"] = "MODIFIED"
                post_data[f"final_action_{anom.id}"] = "Map to priya@example.com"
            elif row_ref == 'row 10': # Invalid date (Mar-14)
                post_data[f"status_{anom.id}"] = "MODIFIED"
                post_data[f"final_action_{anom.id}"] = "Use 2026-03-14"
            elif row_ref == 'row 12': # Outside membership window (remove Meera)
                post_data[f"status_{anom.id}"] = "MODIFIED"
                post_data[f"final_action_{anom.id}"] = "Remove Meera, split among Aisha;Rohan;Priya"
            else:
                post_data[f"status_{anom.id}"] = "APPROVED"
                post_data[f"final_action_{anom.id}"] = "Approved as-is"
                
        # Send post review resolutions
        response = self.client.post(review_url, post_data)
        
        # Check that we redirect to report once all pending anomalies are resolved!
        report_url = reverse('import_report', kwargs={'batch_id': batch.id})
        self.assertRedirects(response, report_url)
        
        # Refresh batch and verify approved status
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'APPROVED')
        
        # 4. Check created models
        created_expenses = Expense.objects.filter(import_batch=batch)
        self.assertEqual(created_expenses.count(), 8)

        # Verify Settlement created for Row 9 (Rohan paid Aisha back)
        created_settlements = Settlement.objects.filter(group=self.group)
        self.assertEqual(created_settlements.count(), 1)
        settlement = created_settlements.first()
        self.assertEqual(settlement.paid_by, self.rohan)
        self.assertEqual(settlement.paid_to, self.aisha)
        self.assertEqual(settlement.amount_inr, Decimal('5000.00'))


        
        # 5. Verify balance changes
        # Let's run balance verification or check net balances
        from balances.engine import get_group_balances
        balances = get_group_balances(self.group)
        
        # Check that the balances run successfully and are non-empty
        self.assertTrue(len(balances) > 0)
        
        # 6. Verify Import Report view page context and rendering
        response = self.client.get(report_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import Audit &amp; Reconciliation Report")
        self.assertContains(response, "Groceries")
        self.assertContains(response, "Parasailing refund")

