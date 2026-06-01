import uuid

class PlategaAPI:
    def __init__(self):
        pass
    
    def create_invoice(self, amount, description, user_id):
        # ЗАГЛУШКА - не настоящий платеж
        payment_id = str(uuid.uuid4())
        return "demo_payment_url", payment_id
    
    def check_payment_status(self, payment_id):
        # ЗАГЛУШКА - всегда успешно
        return True