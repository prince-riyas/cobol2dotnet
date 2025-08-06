from flask import Flask, request, jsonify
from flask_cors import CORS
from .config import AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME, setup_logging, logger, output_dir
import os
import traceback

def create_app():
    app = Flask(__name__)
    CORS(app)

    app.config["AZURE_OPENAI_ENDPOINT"] = AZURE_OPENAI_ENDPOINT
    app.config["AZURE_OPENAI_DEPLOYMENT_NAME"] = AZURE_OPENAI_DEPLOYMENT_NAME
    app.config["UPLOAD_DIR"] = "uploads"
    app.config["output_dir"] = output_dir

    # Initialize comprehensive analysis data
    app.comprehensive_analysis_data = {
        "business_requirements": "",
        "technical_requirements": "",
        "cobol_analysis": {}  # Added for COBOL analysis
    }

    directories = [output_dir, "uploads", os.path.join(output_dir, "analysis"), os.path.join(output_dir, "rag"), os.path.join(output_dir, "standards-rag")]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")

    # Register blueprints
    from .routes import analysis, conversion, cobol_analyzer
    app.register_blueprint(analysis.bp)
    app.register_blueprint(conversion.bp)
    app.register_blueprint(cobol_analyzer)  # Fixed: removed .bp since cobol_analyzer is already the blueprint

    with app.app_context():
        try:
            logger.info("Basic analysis components ready")
            logger.info("Enhanced features will be available through route handlers")
        except Exception as e:
            logger.error(f"Failed to initialize analysis components: {e}")
            logger.info("Application will continue with basic functionality")

    @app.before_request
    def log_request_info():
        logger.debug(f"Request: {request.method} {request.path}")
        logger.debug(f"Remote Address: {request.remote_addr}")
        logger.debug(f"User Agent: {request.headers.get('User-Agent','Unknown')}")

    @app.after_request
    def log_response_info(response):
        logger.debug(f"Response: {response.status_code} for {request.method} {request.path}")
        return response

    @app.errorhandler(404)
    def not_found(error):
        logger.warning(f"404 Error: {request.url} not found")
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"500 Error: {error}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Internal server error"}), 500

    return app