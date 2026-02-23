# Domain layer - aliases and helpers for cleaner business logic
# This file provides semantic aliases to match business domain terms
# while preserving existing database models and relationships

from .models import (
    Objednavka as CustomerOrder,
    Kontrakt as Contract,
    VyrobnaDavka as ProductionBatch,
    OperaciaVyroby as Operation,
    VydajkaZoSkladu as MaterialIssue,
    PrijemkaNaSklad as MaterialReceipt,
    SkladHotovychDielov as FinishedGoodsStock,
    PrijemkaHotovychDielov as FinishedGoodsReceipt,
    VydajkaHotovychDielov as FinishedGoodsIssue,
)

# Job/WorkOrder concept - can be either a ProductionBatch (contract-driven)
# or a CustomerOrder (order-driven production)
class Job:
    """
    Unified interface for production jobs.
    Can wrap either ProductionBatch or CustomerOrder depending on context.
    """

    def __init__(self, instance):
        if isinstance(instance, (ProductionBatch, CustomerOrder)):
            self._instance = instance
        else:
            raise ValueError("Job must wrap ProductionBatch or CustomerOrder")

    @property
    def instance(self):
        return self._instance

    @property
    def number(self):
        """Return job number - either batch number or order number"""
        if isinstance(self._instance, ProductionBatch):
            return self._instance.cislo_davky
        elif isinstance(self._instance, CustomerOrder):
            return self._instance.cislo_objednavky
        return None

    @property
    def contract(self):
        """Get associated contract if any"""
        if isinstance(self._instance, ProductionBatch):
            return self._instance.kontrakt
        elif isinstance(self._instance, CustomerOrder):
            return self._instance.kontrakt
        return None

    @property
    def order(self):
        """Get associated customer order"""
        if isinstance(self._instance, ProductionBatch):
            return self._instance.objednavka
        elif isinstance(self._instance, CustomerOrder):
            return self._instance
        return None

    @property
    def operations(self):
        """Get production operations for this job"""
        return self._instance.operacie.all() if hasattr(self._instance, 'operacie') else []

    @property
    def status(self):
        """Get job status"""
        return self._instance.stav if hasattr(self._instance, 'stav') else None

    def complete_job(self):
        """Mark job as completed and handle stock movements"""
        if isinstance(self._instance, CustomerOrder):
            self._instance.uzavri_zakazku()
        elif isinstance(self._instance, ProductionBatch):
            # Handle batch completion logic
            pass

    @classmethod
    def from_contract_batch(cls, contract, batch_number=None):
        """Create job from contract batch"""
        if batch_number:
            batch = ProductionBatch.objects.filter(
                kontrakt=contract,
                cislo_davky=batch_number
            ).first()
        else:
            batch = ProductionBatch.objects.filter(kontrakt=contract).first()
        return cls(batch) if batch else None

    @classmethod
    def from_order(cls, order_number):
        """Create job from customer order"""
        order = CustomerOrder.objects.filter(cislo_objednavky=order_number).first()
        return cls(order) if order else None

# Stock Movement abstraction
class StockMovement:
    """
    Unified interface for all stock movements (material and finished goods)
    """

    def __init__(self, movement_instance):
        self._instance = movement_instance

    @property
    def type(self):
        """material_issue, material_receipt, finished_goods_issue, finished_goods_receipt"""
        if isinstance(self._instance, MaterialIssue):
            return 'material_issue'
        elif isinstance(self._instance, MaterialReceipt):
            return 'material_receipt'
        elif isinstance(self._instance, FinishedGoodsIssue):
            return 'finished_goods_issue'
        elif isinstance(self._instance, FinishedGoodsReceipt):
            return 'finished_goods_receipt'
        return None

    @property
    def quantity(self):
        return self._instance.mnozstvo

    @property
    def date(self):
        return self._instance.datum

    @property
    def job(self):
        """Get associated job if any"""
        if hasattr(self._instance, 'objednavka') and self._instance.objednavka:
            return Job(self._instance.objednavka)
        return None

    @property
    def contract(self):
        """Get associated contract if any"""
        if hasattr(self._instance, 'kontrakt') and self._instance.kontrakt:
            return self._instance.kontrakt
        elif self.job:
            return self.job.contract
        return None

# Helper functions for common queries
def get_jobs_by_contract(contract):
    """Get all jobs (batches and orders) for a contract"""
    jobs = []

    # Production batches
    for batch in contract.vyrobne_davky.all():
        jobs.append(Job(batch))

    # Orders linked to contract
    for order in contract.objednavky.all():
        jobs.append(Job(order))

    return jobs

def get_stock_movements_for_job(job):
    """Get all stock movements related to a job"""
    movements = []

    # Material issues
    order_instance = job.order.instance if hasattr(job.order, 'instance') else job.order
    for issue in MaterialIssue.objects.filter(objednavka=order_instance):
        movements.append(StockMovement(issue))

    # Finished goods receipts
    for receipt in FinishedGoodsReceipt.objects.filter(objednavka=order_instance):
        movements.append(StockMovement(receipt))

    return movements

def get_total_cost_by_contract(contract):
    """Calculate total costs for a contract across all jobs"""
    total = 0
    for job in get_jobs_by_contract(contract):
        # Add material costs, labor costs, etc.
        # Implementation depends on your cost calculation logic
        pass
    return total