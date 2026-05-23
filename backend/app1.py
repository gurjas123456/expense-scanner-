"""
SmartSpend ML Backend - Flask API for expense tracking and OCR processing
Integrates with production.py OCRService for receipt processing
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import sys
import os
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
import base64
import json
import tempfile
from collections import defaultdict

# Configure encoding for proper UTF-8 support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SMARTSPEND_SECRET_KEY', 'smartspend-dev-secret')
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Configure CORS
FRONTEND_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:4173',
    'http://127.0.0.1:4173',
    'http://localhost:5173',
    'http://127.0.0.1:5173'
]
configured_origins = [
    origin.strip()
    for origin in os.environ.get('FRONTEND_ORIGINS', ','.join(FRONTEND_ORIGINS)).split(',')
    if origin.strip()
]
CORS(
    app,
    supports_credentials=True,
    origins=configured_origins
)

# MongoDB Configuration
MONGO_URI = os.environ.get(
    'MONGO_URI',
    'mongodb+srv://bhumik:8178307875@khaana-khazana.iopbml0.mongodb.net/'
)
MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'EXPENSE')

# Seed user for initial testing
SEED_USER = {
    'username': 'bhumik',
    'name': 'Bhumik',
    'email': 'bhumik@example.com',
    'dob': '2000-01-01',
    'password': 'bhumik'
}

# Global state
mongo_client = None
db = None
users_collection = None
expenses_collection = None
ocr_service = None


def serialize_user(user_doc):
    """Return a user document without sensitive fields."""
    if not user_doc:
        return None
    
    return {
        'id': str(user_doc.get('_id', '')),
        'username': user_doc.get('username', ''),
        'name': user_doc.get('name', ''),
        'email': user_doc.get('email', ''),
        'dob': user_doc.get('dob', '')
    }


def get_database():
    """Get the MongoDB database connection."""
    global mongo_client, db
    
    if db is not None:
        return db
    
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = mongo_client[MONGO_DB_NAME]
        # Verify connection
        db.command('ping')
        print("✅ Connected to MongoDB")
        return db
    except Exception as e:
        print(f"❌ MongoDB connection error: {e}")
        raise


def get_users_collection():
    """Get the MongoDB users collection and ensure indexes exist."""
    global users_collection
    
    if users_collection is not None:
        return users_collection
    
    try:
        database = get_database()
        users_collection = database['users']
        users_collection.create_index('email', unique=True)
        users_collection.create_index('username', unique=True)
        ensure_seed_user()
        return users_collection
    except Exception as e:
        print(f"Error getting users collection: {e}")
        raise


def get_expenses_collection():
    """Get the MongoDB expenses collection."""
    global expenses_collection
    
    if expenses_collection is not None:
        return expenses_collection
    
    try:
        database = get_database()
        expenses_collection = database['expenses']
        expenses_collection.create_index('username')
        expenses_collection.create_index('date')
        return expenses_collection
    except Exception as e:
        print(f"Error getting expenses collection: {e}")
        raise


def ensure_seed_user():
    """Ensure the initial user account exists in MongoDB."""
    if users_collection is None:
        return
    
    try:
        existing_user = users_collection.find_one({'email': SEED_USER['email']})
        if existing_user:
            return
        
        users_collection.insert_one({
            'username': SEED_USER['username'],
            'name': SEED_USER['name'],
            'email': SEED_USER['email'],
            'dob': SEED_USER['dob'],
            'password_hash': generate_password_hash(SEED_USER['password']),
            'created_at': datetime.utcnow().isoformat()
        })
        print(f"✅ Created seed user: {SEED_USER['username']}")
    except Exception as e:
        print(f"Error creating seed user: {e}")


def get_current_user():
    """Load the authenticated user from the current session."""
    username = session.get('username')
    if not username:
        return None
    
    try:
        collection = get_users_collection()
        return collection.find_one({'username': username})
    except PyMongoError as e:
        print(f"MongoDB session lookup failed: {e}")
        return None


def is_authenticated():
    """Check if user is authenticated."""
    return get_current_user() is not None


def get_ocr_service():
    """Load the OCRService from production.py."""
    global ocr_service
    
    if ocr_service is not None:
        return ocr_service
    
    try:
        from production import OCRService
        models_dir = os.path.dirname(os.path.abspath(__file__))
        ocr_service = OCRService(models_dir=models_dir, use_gpu=False)
        print("✅ OCR Service loaded successfully")
        return ocr_service
    except ImportError as e:
        print(f"⚠️ Could not load production.py: {e}")
        print("   OCR functionality will be limited")
        return None
    except Exception as e:
        print(f"❌ Error initializing OCR service: {e}")
        return None


# ==================== Authentication Routes ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user."""
    try:
        data = request.get_json(silent=True) or {}
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'name']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        users = get_users_collection()
        
        # Check if user already exists
        if users.find_one({'email': data['email']}):
            return jsonify({'error': 'Email already registered'}), 400
        
        if users.find_one({'username': data['username']}):
            return jsonify({'error': 'Username already taken'}), 400
        
        # Create new user
        new_user = {
            'username': data['username'],
            'email': data['email'],
            'name': data['name'],
            'dob': data.get('dob', ''),
            'password_hash': generate_password_hash(data['password']),
            'created_at': datetime.utcnow().isoformat()
        }
        
        result = users.insert_one(new_user)
        
        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'user': serialize_user(users.find_one({'_id': result.inserted_id}))
        }), 201
        
    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user."""
    try:
        data = request.get_json(silent=True) or {}
        
        if not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password required'}), 400
        
        users = get_users_collection()
        user = users.find_one({'username': data['username']})
        
        if not user or not check_password_hash(user['password_hash'], data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        session['username'] = user['username']
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': serialize_user(user)
        })
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user."""
    try:
        session.clear()
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/me', methods=['GET'])
def get_me():
    """Get current authenticated user."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        return jsonify({
            'success': True,
            'user': serialize_user(user)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Expense Routes ====================

@app.route('/api/expenses', methods=['GET', 'POST'])
def expenses():
    """API endpoint to manage expenses."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        expenses = get_expenses_collection()
        
        if request.method == 'POST':
            # Add new expense
            data = request.get_json(silent=True) or {}
            
            # Validate required fields
            required_fields = ['vendor', 'amount', 'category', 'date']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            # Validate amount
            try:
                amount_value = float(data['amount'])
                if amount_value <= 0:
                    return jsonify({'error': 'Amount must be greater than 0'}), 400
            except (ValueError, TypeError):
                return jsonify({'error': 'Amount must be a valid number'}), 400
            
            # Validate vendor
            if not str(data['vendor']).strip():
                return jsonify({'error': 'Vendor name cannot be empty'}), 400
            
            # Validate category
            if not str(data['category']).strip():
                return jsonify({'error': 'Category cannot be empty'}), 400
            
            # Create expense document
            expense_doc = {
                'username': user['username'],
                'vendor': data['vendor'],
                'amount': float(data['amount']),
                'currency': data.get('currency', 'INR'),
                'category': data['category'],
                'date': data['date'],
                'items': data.get('items', []),
                'description': data.get('description', ''),
                'created_at': datetime.utcnow().isoformat()
            }
            
            result = expenses.insert_one(expense_doc)
            
            print(f"💾 Added expense: {expense_doc['vendor']} - {expense_doc['currency']} {expense_doc['amount']}")
            
            expense_doc['_id'] = str(result.inserted_id)
            
            return jsonify({
                'success': True,
                'message': 'Expense added successfully',
                'expense': {
                    'id': str(result.inserted_id),
                    'vendor': expense_doc['vendor'],
                    'amount': expense_doc['amount'],
                    'currency': expense_doc['currency'],
                    'category': expense_doc['category'],
                    'date': expense_doc['date'],
                    'items': expense_doc['items'],
                    'description': expense_doc['description'],
                    'created_at': expense_doc['created_at']
                }
            }), 201
        
        else:
            # Get expenses with optional filtering
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            category = request.args.get('category')
            
            # Build query filter
            query = {'username': user['username']}
            
            if start_date:
                query['date'] = {'$gte': start_date}
            if end_date:
                if 'date' in query:
                    query['date']['$lte'] = end_date
                else:
                    query['date'] = {'$lte': end_date}
            if category and category != 'All Categories':
                query['category'] = category
            
            # Execute query
            result = list(expenses.find(query).sort('date', -1))
            
            # Format results
            formatted_expenses = []
            for expense in result:
                formatted_expenses.append({
                    'id': str(expense['_id']),
                    'vendor': expense['vendor'],
                    'amount': expense['amount'],
                    'currency': expense['currency'],
                    'category': expense['category'],
                    'date': expense['date'],
                    'items': expense.get('items', []),
                    'description': expense.get('description', ''),
                    'created_at': expense['created_at']
                })
            
            return jsonify({
                'success': True,
                'expenses': formatted_expenses,
                'total': len(formatted_expenses)
            })
        
    except Exception as e:
        print(f"Error managing expenses: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/expenses/<expense_id>', methods=['DELETE', 'PUT'])
def manage_expense(expense_id):
    """Delete or update an expense."""
    try:
        from bson.objectid import ObjectId
        
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        expenses = get_expenses_collection()
        
        try:
            object_id = ObjectId(expense_id)
        except Exception:
            return jsonify({'error': 'Invalid expense ID'}), 400
        
        expense = expenses.find_one({'_id': object_id, 'username': user['username']})
        if not expense:
            return jsonify({'error': 'Expense not found'}), 404
        
        if request.method == 'DELETE':
            expenses.delete_one({'_id': object_id})
            return jsonify({
                'success': True,
                'message': 'Expense deleted successfully'
            })
        
        elif request.method == 'PUT':
            data = request.get_json(silent=True) or {}
            
            # Build update document
            update_doc = {}
            if 'vendor' in data:
                update_doc['vendor'] = data['vendor']
            if 'amount' in data:
                try:
                    update_doc['amount'] = float(data['amount'])
                except (ValueError, TypeError):
                    return jsonify({'error': 'Amount must be a valid number'}), 400
            if 'category' in data:
                update_doc['category'] = data['category']
            if 'date' in data:
                update_doc['date'] = data['date']
            if 'currency' in data:
                update_doc['currency'] = data['currency']
            if 'items' in data:
                update_doc['items'] = data['items']
            if 'description' in data:
                update_doc['description'] = data['description']
            
            if not update_doc:
                return jsonify({'error': 'No fields to update'}), 400
            
            update_doc['updated_at'] = datetime.utcnow().isoformat()
            
            expenses.update_one({'_id': object_id}, {'$set': update_doc})
            
            return jsonify({
                'success': True,
                'message': 'Expense updated successfully'
            })
    
    except Exception as e:
        print(f"Error managing expense: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/expenses/clear', methods=['DELETE'])
def clear_expenses():
    """Clear all expenses for current user (for testing)."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        expenses = get_expenses_collection()
        result = expenses.delete_many({'username': user['username']})
        
        return jsonify({
            'success': True,
            'message': f'Cleared {result.deleted_count} expenses'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Analytics Routes ====================

@app.route('/api/analytics', methods=['GET'])
def analytics():
    """Get expense analytics data."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        expenses = get_expenses_collection()
        user_expenses = list(expenses.find({'username': user['username']}))
        
        if not user_expenses:
            return jsonify({
                'success': True,
                'categoryData': [],
                'monthlyData': [],
                'totalExpenses': 0,
                'averageExpense': 0,
                'expenseCount': 0
            })
        
        # Category-wise analysis
        category_totals = defaultdict(float)
        monthly_totals = defaultdict(float)
        
        for expense in user_expenses:
            try:
                # Convert to INR for consistency
                amount_inr = expense['amount']
                if expense.get('currency') == 'USD':
                    amount_inr *= 80  # Simple conversion rate
                
                category_totals[expense['category']] += amount_inr
                
                # Group by month
                try:
                    expense_date = datetime.strptime(expense['date'], '%Y-%m-%d')
                    month_key = expense_date.strftime('%Y-%m')
                except (ValueError, TypeError):
                    month_key = datetime.utcnow().strftime('%Y-%m')
                
                monthly_totals[month_key] += amount_inr
            except Exception as e:
                print(f"Error processing expense for analytics: {e}")
                continue
        
        # Prepare category data
        category_data = [
            {'name': category, 'value': round(amount, 2)}
            for category, amount in sorted(category_totals.items())
        ]
        
        # Prepare monthly data
        monthly_data = [
            {'month': month, 'amount': round(amount, 2)}
            for month, amount in sorted(monthly_totals.items())
        ]
        
        # Calculate totals
        total_expenses = sum(category_totals.values())
        average_expense = total_expenses / len(user_expenses) if user_expenses else 0
        
        return jsonify({
            'success': True,
            'categoryData': category_data,
            'monthlyData': monthly_data,
            'totalExpenses': round(total_expenses, 2),
            'averageExpense': round(average_expense, 2),
            'expenseCount': len(user_expenses)
        })
    
    except Exception as e:
        print(f"Error calculating analytics: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== OCR Routes ====================

@app.route('/api/ocr/process-receipt', methods=['POST'])
def process_receipt():
    """Process a receipt image using OCR."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        service = get_ocr_service()
        if not service:
            return jsonify({'error': 'OCR service not available'}), 503
        
        # Check if image is provided as base64 or file
        data = request.get_json(silent=True) or {}
        
        if 'image_base64' in data:
            # Decode base64 image
            try:
                image_data = base64.b64decode(data['image_base64'])
                # Save to temporary file
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp.write(image_data)
                    temp_path = tmp.name
            except Exception as e:
                return jsonify({'error': f'Invalid image format: {e}'}), 400
        
        elif 'file' in request.files:
            # Handle file upload
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                file.save(tmp.name)
                temp_path = tmp.name
        
        else:
            return jsonify({'error': 'No image provided (use image_base64 or file)'}), 400
        
        # Process receipt
        try:
            result = service.process_receipt(temp_path)
            
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            
            return jsonify({
                'success': True,
                'category': result['category'],
                'amount': result['amount'],
                'all_amounts': result['all_amounts'],
                'raw_text': result['raw_text'],
                'cleaned_text': result['cleaned_text'],
                'ocr_backend': result['ocr_backend']
            })
        
        except Exception as e:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            
            return jsonify({'error': f'OCR processing error: {str(e)}'}), 500
    
    except Exception as e:
        print(f"Error processing receipt: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== Health Check Routes ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        service = get_ocr_service()
        
        return jsonify({
            'status': 'healthy',
            'ocr_service': 'available' if service else 'unavailable',
            'mongo_connected': db is not None,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503


@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint."""
    return jsonify({
        'message': 'SmartSpend backend is running!',
        'timestamp': datetime.utcnow().isoformat()
    })


# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors."""
    return jsonify({'error': 'Internal server error'}), 500


# ==================== Main ====================

if __name__ == '__main__':
    print("🚀 Starting SmartSpend ML Backend...")
    print("📊 Backend URL: http://localhost:5000")
    
    # Initialize services
    try:
        get_users_collection()
        get_expenses_collection()
        get_ocr_service()
    except Exception as e:
        print(f"⚠️ Warning: Some services failed to initialize: {e}")
    
    debug_enabled = os.environ.get('FLASK_DEBUG', '0') == '1'
    
    app.run(
        debug=debug_enabled,
        use_reloader=False,
        host='0.0.0.0',
        port=5000,
        threaded=True
    )
