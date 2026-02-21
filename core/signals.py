from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from .models import Objednavka, VyrobnaDavka, PrijemkaHotovychDielov

def _get_order_from_instance(inst):
    for attr in ("objednavka", "zakazka", "order"):
        if hasattr(inst, attr):
            return getattr(inst, attr)
    for fk in ("objednavka_id", "zakazka_id", "order_id"):
        val = getattr(inst, fk, None)
        if val:
            try:
                return Objednavka.objects.get(pk=val)
            except Objednavka.DoesNotExist:
                return None
    return None

def _compute_produced_total(order):
    if not order:
        return 0
    for prop in ("vyrobene_mnozstvo", "vyrobene_kusy", "vyrobene"):
        val = getattr(order, prop, None)
        if isinstance(val, (int, float)):
            return val
    qs = VyrobnaDavka.objects.filter(objednavka=order)
    if not qs.exists():
        return 0
    for field in ("mnozstvo", "mnozstvo_davky", "mnozstvo_vyrobene", "vyrobene_kusy", "vyrobene"):
        try:
            agg = qs.aggregate(total=Sum(field))["total"]
            if agg is not None:
                return agg
        except Exception:
            continue
    total = 0
    for d in qs:
        for field in ("mnozstvo", "mnozstvo_davky", "mnozstvo_vyrobene", "vyrobene_kusy", "vyrobene"):
            v = getattr(d, field, None)
            if isinstance(v, (int, float)):
                total += v
                break
    return total

def _get_required_total(order):
    for attr in ("mnozstvo", "pocet_kusov", "pocet_kusov_celkovo"):
        val = getattr(order, attr, None)
        if isinstance(val, (int, float)):
            return val
    return None

def _maybe_close_order(order):
    if not order:
        return
    produced = _compute_produced_total(order)
    required = _get_required_total(order)
    if required is None:
        return
    if produced >= required and getattr(order, "stav", None) != "hotovo":
        order.stav = "hotovo"
        order.save(update_fields=["stav"])

@receiver(post_save, sender=VyrobnaDavka)
@receiver(post_delete, sender=VyrobnaDavka)
def vyrobna_davka_changed(sender, instance, **kwargs):
    order = _get_order_from_instance(instance)
    _maybe_close_order(order)

@receiver(post_save, sender=PrijemkaHotovychDielov)
@receiver(post_delete, sender=PrijemkaHotovychDielov)
def prijemka_hotovych_changed(sender, instance, **kwargs):
    order = _get_order_from_instance(instance)
    _maybe_close_order(order)