from flask import Blueprint, request, jsonify, current_app
from ..config import logger, AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME
from openai import AzureOpenAI
import json, traceback, os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from ..utils.prompts import (
    create_business_requirements_prompt,
    create_technical_requirements_prompt,
    create_target_structure_prompt
)
from ..utils.endpoint import sendtoEGPT
from ..utils.logs import (
    log_request_details,
    log_processing_step,
    log_gpt_interaction
)
from ..utils.response import extract_json_from_response
from ..utils.file_classifier import classify_uploaded_files
# from ..utils.rag_indexer import load_vector_store, query_vector_store, index_files_for_rag
from ..utils.cobol_analyzer import create_cobol_json
 
bp = Blueprint('analysis', __name__, url_prefix='/cobo')
 
# client = AzureOpenAI(
#     api_key=AZURE_OPENAI_API_KEY,
#     api_version="2023-05-15",
#     azure_endpoint=AZURE_OPENAI_ENDPOINT,
# )
 
def enhanced_classify_files(file_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Enhanced file classification using existing classifier"""
    logger.info("=== ENHANCED FILE CLASSIFICATION STARTED ===")
 
    basic_classified = classify_uploaded_files(file_data)
 
    enhanced = {
        "COBOL Code": [],
        "JCL": [],
        "Copybooks": [],
        "VSAM Definitions": [],
        "BMS Maps": [],
        "Control Files": [],
        "Standards Documents": [],
        "Unknown": []
    }
 
    for category, files in basic_classified.items():
        if category in enhanced:
            for file_info in files:
                if isinstance(file_info, dict) and "fileName" in file_info:
                    enhanced_file_info = {
                        "fileName": file_info["fileName"],
                        "content": file_info.get("content", ""),
                        "size": len(file_info.get("content", "")),
                        "extension": Path(file_info["fileName"]).suffix.lower(),
                        "lines": len(str(file_info.get("content", "")).split('\n'))
                    }
                    enhanced[category].append(enhanced_file_info)
 
    logger.info("=== ENHANCED FILE CLASSIFICATION COMPLETED ===")
    return enhanced
 
def get_cobol_files_for_analysis(classified_files: Dict[str, List[Dict[str, Any]]]) -> Dict[str, str]:
    """Extract COBOL-related files for analysis"""
    analysis_files = {}
 
    for file_info in classified_files.get("COBOL Code", []):
        analysis_files[file_info["fileName"]] = file_info["content"]
 
    for file_info in classified_files.get("Copybooks", []):
        analysis_files[file_info["fileName"]] = file_info["content"]
 
    for file_info in classified_files.get("JCL", []):
        analysis_files[file_info["fileName"]] = file_info["content"]
 
    return analysis_files
 
def reverse_engineer_cobol_code(cobol_code: str, project_id: str, include_dependencies: bool = True) -> Dict[str, Any]:
    """
    Perform comprehensive reverse engineering of COBOL code using GPT analysis.
 
    Args:
        cobol_code: The COBOL source code to analyze
        project_id: Unique identifier for the project
        include_dependencies: Whether to analyze external dependencies
 
    Returns:
        Dictionary containing comprehensive reverse engineering analysis
    """
    logger.info(f"=== REVERSE ENGINEERING STARTED for project: {project_id} ===")
 
    if not cobol_code.strip():
        logger.warning("No COBOL code provided for reverse engineering")
        return {"error": "No COBOL code available for reverse engineering"}
 
    try:
        # Comprehensive reverse engineering system message
        reverse_engineering_msgs = [
            {
                "role": "system",
                "content": (
                    "You are a senior COBOL reverse engineering expert with deep knowledge of mainframe systems, legacy architectures, and business process analysis."
                    "Your task is to perform comprehensive reverse engineering of COBOL programs to understand their complete structure, purpose, and business logic."
                    "Implement business rules in detailed give working of business rules, logic extraction properly"
                    "Give Detailed business extraction of the code.Dont give one liners, make 3-4 sentences"
 
                    "REVERSE ENGINEERING ANALYSIS AREAS:\n"
                    "1. PROGRAM STRUCTURE ANALYSIS\n"
                    "   - Division organization and purpose\n"
                    "   - Section and paragraph hierarchy\n"
                    "   - Control flow and program logic\n"
                    "   - Entry points and exit conditions\n\n"
 
                    "2. DATA FLOW ANALYSIS\n"
                    "   - Input/output file structures\n"
                    "   - Data transformation processes\n"
                    "   - Working storage usage patterns\n"
                    "   - Linkage section parameter handling\n"
                    "   - Copybook dependencies and data sharing\n\n"
 
                    "3. BUSINESS LOGIC EXTRACTION\n"
                    "   - Core business rules and validations\n"
                    "   - Calculation algorithms and formulas\n"
                    "   - Decision-making logic and conditions\n"
                    "   - Error handling and exception processing\n"
                    "   - Business process workflows\n\n"
 
                    "4. SYSTEM INTEGRATION ANALYSIS\n"
                    "   - CICS transaction processing\n"
                    "   - Database operations (DB2, IMS)\n"
                    "   - VSAM file operations and access patterns\n"
                    "   - JCL integration and job dependencies\n"
                    "   - BMS screen handling and user interactions\n\n"
 
                    "5. DEPENDENCY MAPPING\n"
                    "   - External program calls and subroutines\n"
                    "   - Copybook dependencies and shared data\n"
                    "   - File system dependencies\n"
                    "   - System resource requirements\n"
                    "   - External service dependencies\n\n"
 
                    "6. PERFORMANCE CHARACTERISTICS\n"
                    "   - Processing bottlenecks and optimization opportunities\n"
                    "   - Memory usage patterns\n"
                    "   - File access patterns and efficiency\n"
                    "   - CPU-intensive operations\n\n"
 
                    "OUTPUT FORMAT (JSON):\n"
                    "{\n"
                    '  "programMetadata": {\n'
                    '    "programName": "Program identifier",\n'
                    '    "programType": "Batch/Online/Utility/Service",\n'
                    '    "estimatedAge": "Estimated development era",\n'
                    '    "complexityLevel": "Low/Medium/High/Very High",\n'
                    '    "mainPurpose": "Primary business function",\n'
                    '    "businessDomain": "Business area (Finance, HR, etc.)"\n'
                    '  },\n'
                    '  "structuralAnalysis": {\n'
                    '    "divisions": [\n'
                    '      {\n'
                    '        "name": "Division name",\n'
                    '        "purpose": " Detailed Division purpose",\n'
                    '        "sections": [\n'
                    '          {\n'
                    '            "name": " Section name",\n'
                    '            "purpose": "Detailed Section purpose",\n'
                    '            "paragraphs": ["List of paragraphs"]\n'
                    '          }\n'
                    '        ]\n'
                    '      }\n'
                    '    ],\n'
                    '    "controlFlow": {\n'
                    '      "entryPoints": ["Program entry points"],\n'
                    '      "mainProcessing": "Main processing logic description",\n'
                    '      "exitConditions": ["Program exit conditions"],\n'
                    '      "errorHandling": "Error handling approach"\n'
                    '    }\n'
                    '  },\n'
                    '  "dataFlowAnalysis": {\n'
                    '    "inputFiles": [\n'
                    '      {\n'
                    '        "fileName": "Input file name",\n'
                    '        "recordFormat": "Detailed Record structure description",\n'
                    '        "accessMethod": "Sequential/Indexed/Random",\n'
                    '        "usage": "How the file is used in processing"\n'
                    '      }\n'
                    '    ],\n'
                    '    "outputFiles": [\n'
                    '      {\n'
                    '        "fileName": "Output file name",\n'
                    '        "recordFormat": "Record structure description",\n'
                    '        "generationLogic": "How output is generated"\n'
                    '      }\n'
                    '    ],\n'
                    '    "workingStorage": [\n'
                    '      {\n'
                    '        "name": "Variable name",\n'
                    '        "purpose": "Variable purpose",\n'
                    '        "usage": "How variable is used",\n'
                    '        "dataType": "Data type and size"\n'
                    '      }\n'
                    '    ],\n'
                    '    "dataTransformations": [\n'
                    '      {\n'
                    '        "transformation": "Data transformation description",\n'
                    '        "source": "Source data",\n'
                    '        "target": "Target data",\n'
                    '        "businessPurpose": "Why this transformation is needed"\n'
                    '      }\n'
                    '    ]\n'
                    '  },\n'
                    '  "businessLogic": {\n'
                    '    "coreBusinessRules": [\n'
                    '      {\n'
                    '        "rule": "Business rule description",\n'
                    '        "implementation": "How rule is implemented",\n'
                    '        "conditions": "When rule applies",\n'
                    '        "businessImpact": "Impact on business process"\n'
                    '      }\n'
                    '    ],\n'
                    '    "calculations": [\n'
                    '      {\n'
                    '        "calculation": "Calculation description",\n'
                    '        "formula": "Mathematical formula or logic",\n'
                    '        "businessPurpose": "Why calculation is needed",\n'
                    '        "accuracy": "Accuracy requirements"\n'
                    '      }\n'
                    '    ],\n'
                    '    "validations": [\n'
                    '      {\n'
                    '        "validation": "Validation description",\n'
                    '        "criteria": "Validation criteria",\n'
                    '        "errorHandling": "How validation errors are handled"\n'
                    '      }\n'
                    '    ]\n'
                    '  },\n'
                    '  "systemIntegration": {\n'
                    '    "cicsOperations": [\n'
                    '      {\n'
                    '        "operation": "CICS command",\n'
                    '        "purpose": "What it accomplishes",\n'
                    '        "resources": ["Resources accessed"]\n'
                    '      }\n'
                    '    ],\n'
                    '    "databaseOperations": [\n'
                    '      {\n'
                    '        "operation": "Database operation",\n'
                    '        "tables": ["Table names"],\n'
                    '        "purpose": "Business purpose"\n'
                    '      }\n'
                    '    ],\n'
                    '    "vsamOperations": [\n'
                    '      {\n'
                    '        "operation": "VSAM operation",\n'
                    '        "file": "VSAM file name",\n'
                    '        "purpose": "Business purpose"\n'
                    '      }\n'
                    '    ],\n'
                    '    "bmsOperations": [\n'
                    '      {\n'
                    '        "operation": "BMS operation",\n'
                    '        "screen": "Screen name",\n'
                    '        "purpose": "User interaction purpose"\n'
                    '      }\n'
                    '    ]\n'
                    '  },\n'
                    '  "dependencies": {\n'
                    '    "externalPrograms": [\n'
                    '      {\n'
                    '        "programName": "Called program name",\n'
                    '        "purpose": "Why it is called",\n'
                    '        "parameters": ["Parameters passed"],\n'
                    '        "returnValues": ["Values returned"]\n'
                    '      }\n'
                    '    ],\n'
                    '    "copybooks": [\n'
                    '      {\n'
                    '        "copybookName": "Copybook name",\n'
                    '        "purpose": "What it contains",\n'
                    '        "dataStructures": ["Key data structures"]\n'
                    '      }\n'
                    '    ],\n'
                    '    "systemResources": [\n'
                    '      {\n'
                    '        "resource": "System resource name",\n'
                    '        "type": "File/Queue/Database/etc",\n'
                    '        "usage": "How resource is used"\n'
                    '      }\n'
                    '    ]\n'
                    '  },\n'
                    '  "performanceAnalysis": {\n'
                    '    "bottlenecks": [\n'
                    '      {\n'
                    '        "bottleneck": "Performance bottleneck description",\n'
                    '        "impact": "Performance impact",\n'
                    '        "optimization": "Potential optimization"\n'
                    '      }\n'
                    '    ],\n'
                    '    "memoryUsage": {\n'
                    '      "workingStorage": "Working storage usage pattern",\n'
                    '      "dynamicAllocation": "Dynamic memory allocation",\n'
                    '      "optimization": "Memory optimization opportunities"\n'
                    '    },\n'
                    '    "processingEfficiency": {\n'
                    '      "fileAccess": "File access efficiency",\n'
                    '      "loops": "Loop efficiency analysis",\n'
                    '      "calculations": "Calculation efficiency"\n'
                    '    }\n'
                    '  },\n'
                    '  "modernizationInsights": {\n'
                    '    "legacyPatterns": [\n'
                    '      {\n'
                    '        "pattern": "Legacy pattern identified",\n'
                    '        "modernEquivalent": "Modern equivalent approach",\n'
                    '        "migrationComplexity": "Low/Medium/High"\n'
                    '      }\n'
                    '    ],\n'
                    '    "businessValue": {\n'
                    '      "criticalFunctions": ["Critical business functions"],\n'
                    '      "riskAreas": ["High-risk areas for modernization"],\n'
                    '      "opportunities": ["Modernization opportunities"]\n'
                    '    },\n'
                    '    "recommendations": [\n'
                    '      {\n'
                    '        "recommendation": "Modernization recommendation",\n'
                    '        "rationale": "Why this recommendation",\n'
                    '        "effort": "Estimated effort level"\n'
                    '      }\n'
                    '    ]\n'
                    '  }\n'
                    "}\n\n"
 
                    "ANALYSIS INSTRUCTIONS:\n"
                    "- Perform deep analysis of ALL COBOL divisions and sections\n"
                    "- Identify ALL business rules and logic patterns\n"
                    "- Map ALL data dependencies and relationships\n"
                    "- Analyze performance characteristics and bottlenecks\n"
                    "- Document ALL system integrations and dependencies\n"
                    "- Provide specific modernization insights and recommendations\n"
                    "- Consider mainframe-specific constraints and characteristics\n"
                    "- Focus on business value and operational impact\n"
                    "- Identify legacy patterns and their modern equivalents"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Please perform comprehensive reverse engineering analysis of the following COBOL program. "
                    f"This program may contain complex business logic, multiple system integrations, and legacy patterns. "
                    f"Provide a thorough reverse engineering analysis that captures all aspects of the program:\n\n"
                    f"COBOL Program:\n"
                    f"```cobol\n{cobol_code}\n```\n\n"
                    f"Please ensure your analysis covers:\n"
                    f"1. Complete program structure and control flow\n"
                    f"2. All data flow patterns and transformations\n"
                    f"3. Business logic extraction and business rules\n"
                    f"4. System integration points and dependencies\n"
                    f"5. Performance characteristics and optimization opportunities\n"
                    f"6. Legacy patterns and modernization insights\n"
                    f"7. Risk assessment and business value analysis"
                )
            }
        ]
 
        log_processing_step("Calling GPT for reverse engineering analysis", {
            "cobol_code_length": len(cobol_code),
            "project_id": project_id,
            "include_dependencies": include_dependencies,
            "analysis_type": "reverse_engineering"
        }, "REVERSE_ENGINEERING")
 
        # reverse_engineering_response = sendtoEGPT(reverse_engineering_msgs)
 
        # log_gpt_interaction("REVERSE_ENGINEERING", AZURE_OPENAI_DEPLOYMENT_NAME, reverse_engineering_msgs, reverse_engineering_response)
 
        # reverse_engineering_json = extract_json_from_response(reverse_engineering_response)
 
        # Save reverse engineering analysis JSON
        output_dir = os.path.join("output", "analysis", project_id)
        os.makedirs(output_dir, exist_ok=True)
        reverse_engineering_path = os.path.join(output_dir, "reverse_engineering_analysis.json")
 
        # with open(reverse_engineering_path, "w", encoding='utf-8') as f:
        #     json.dump(reverse_engineering_json, f, indent=2, ensure_ascii=False)
 
        # logger.info(f"Reverse engineering analysis saved to: {reverse_engineering_path}")
 
        # logger.info("=== REVERSE ENGINEERING COMPLETED ===")
        return reverse_engineering_json
 
    except Exception as e:
        logger.error(f"Error performing reverse engineering: {str(e)}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "project_id": project_id
        }
 
def create_target_structure_analysis(project_id: str, file_data: Dict[str, Any], classified_files: Dict[str, List[Dict[str, Any]]], business_requirements: Dict[str, Any] = None, technical_requirements: Dict[str, Any] = None, reverse_engineering: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create target structure analysis using GPT"""
    logger.info(f"=== TARGET STRUCTURE ANALYSIS STARTED for project: {project_id} ===")
 
    # Combine all COBOL-related content
    cobol_content = ""
    for category in ["COBOL Code", "Copybooks", "JCL", "VSAM Definitions", "BMS Maps", "Control Files"]:
        for file_info in classified_files.get(category, []):
            cobol_content += f"\n\n=== {file_info['fileName']} ===\n{file_info['content']}"
 
    if not cobol_content.strip():
        logger.warning("No COBOL content found for target structure analysis")
        return {"error": "No COBOL content available for analysis"}
 
    # Use the dynamic, detailed prompt
    structure_prompt = create_target_structure_prompt( cobol_content)
 
    # Add business and technical requirements context if available
    requirements_context = ""
    if business_requirements and technical_requirements:
        requirements_context = f"\n\nBUSINESS REQUIREMENTS:\n{json.dumps(business_requirements, indent=2)}\n\nTECHNICAL REQUIREMENTS:\n{json.dumps(technical_requirements, indent=2)}"
        structure_prompt += requirements_context
 
 
    # Add reverse engineering context if available
    if reverse_engineering:
        reverse_engineering_context = f"\n\nREVERSE ENGINEERING ANALYSIS:\n{json.dumps(reverse_engineering, indent=2)}"
        structure_prompt += reverse_engineering_context
 
    try:
        structure_msgs = [
            {
                "role": "system",
                "content": (
                    "You are a seasoned software architect with deep expertise in migrating COBOL-based legacy systems to modern .NET 8 WebAPI solutions. "
                    "You are proficient in both legacy mainframe technologies and contemporary .NET 8 layered architectures, including the Model-Controller pattern. "
                    "Your role is to analyze COBOL source code and all associated artifacts—such as JCL, VSAM files, Copybooks, CICS programs, BMS Maps, and Control Files—to architect a clean, maintainable backend in .NET 8. "
                    "The target system must follow .NET 8 best practices, enforcing a clear separation of concerns. It should include Controllers, Models, Services, Repositories, Interfaces, "
                    "A  Data Access Layer using ApplicationDbContext with EF Core integration, and optionally Middleware, Logging, and JWT-based Security where applicable. "
                    "Ensure business logic is preserved and appropriately distributed across Services and Controllers. "
                    "Incorporate provided business or technical requirements to guide architectural and design decisions. "
                    "Generate a production-ready .NET 8 solution that is modular, scalable, and testable. "
                    "Also generate the necessary project files including the `.csproj` file, `Program.cs`, and `appsettings.json` as part of the output."
                )
            },
            {
                "role": "user",
                "content": structure_prompt
            }
        ]
 
        log_processing_step("Calling GPT for target structure analysis", {
            "prompt_length": len(structure_prompt),
            "project_id": project_id,
            "has_requirements": bool(business_requirements and technical_requirements),
        }, "TARGET_STRUCTURE")
 
        structure_response = sendtoEGPT(
           structure_msgs,
 
        )
 
        log_gpt_interaction("TARGET_STRUCTURE", AZURE_OPENAI_DEPLOYMENT_NAME, structure_msgs, structure_response)
 
        structure_json = extract_json_from_response(structure_response)
 
        # Save target structure JSON
        output_dir = os.path.join("output", "analysis", project_id)
        os.makedirs(output_dir, exist_ok=True)
        structure_path = os.path.join(output_dir, "target_structure.json")
        with open(structure_path, "w") as f:
            json.dump(structure_json, f, indent=2)
        logger.info(f"Target structure saved to: {structure_path}")
 
        logger.info("=== TARGET STRUCTURE ANALYSIS COMPLETED ===")
        return structure_json
 
    except Exception as e:
        logger.error(f"Error creating target structure analysis: {str(e)}")
        return {"error": str(e)}
 
@bp.route("/analysis-status", methods=["GET"])
def analysis_status():
    """Return the current analysis status for the project"""
    try:
        project_id = current_app.comprehensive_analysis_data.get("project_id", "N/A")
        cobol_files = current_app.comprehensive_analysis_data.get("cobol_files", {})
        rag_status = {
            "standards_rag_active": hasattr(current_app, 'standards_documents') and bool(current_app.standards_documents),
            "project_rag_active": bool(cobol_files)
        }
        return jsonify({
            "project_id": project_id,
            "project_files_loaded": len(cobol_files),
            "conversion_context_ready": bool(cobol_files and current_app.comprehensive_analysis_data.get("analysis_results")),
            "rag_status": rag_status
        })
    except Exception as e:
        logger.error(f"Error fetching analysis status: {e}")
        return jsonify({"error": str(e)}), 500
 
@bp.route("/analyze-requirements", methods=["POST"])
def analyze_requirements():
    """
    Enhanced flow:
    1) Classify uploaded files
    2) Generate cobol_analysis.json
    4) Run GPT for business & technical requirements
    5) Generate target_structure.json.
    6) Index files for RAG
    """
    try:
        data = request.json
        log_request_details("ANALYZE REQUIREMENTS", data)
        if not data:
            return jsonify({"error": "No data provided"}), 400
 
        project_id = data.get("projectId")
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
 
        log_processing_step("Parsing request data", {
            "has_file_data": "file_data" in data,
            "source_language": data.get("sourceLanguage"),
            "target_language": data.get("targetLanguage"),
            "project_id": project_id
        }, 1)
 
        # 1) CLASSIFY FILES
        file_data = data.get("file_data", {})
        if isinstance(file_data, str):
            file_data = json.loads(file_data)
 
        if not file_data:
            return jsonify({"error": "No file data provided"}), 400
 
        classified = enhanced_classify_files(file_data)
 
        log_processing_step("File classification completed", {
            "total_files": sum(len(files) for files in classified.values()),
            "cobol_files": len(classified.get("COBOL Code", [])),
            "copybooks": len(classified.get("Copybooks", [])),
            "jcl_files": len(classified.get("JCL", []))
        }, 2)
 
        # 2) GENERATE COBOL ANALYSIS JSON
        log_processing_step("Generating COBOL analysis JSON", {"project_id": project_id}, 3)
        cobol_json = create_cobol_json(project_id)
 
        # Save COBOL JSON
        output_dir = os.path.join("output", "analysis", project_id)
        os.makedirs(output_dir, exist_ok=True)
        analysis_path = os.path.join(output_dir, "cobol_analysis.json")
        with open(analysis_path, "w") as f:
            json.dump(cobol_json, f, indent=2)
        logger.info(f"COBOL JSON created at: {analysis_path}")
 
        cobol_list = [f["content"] for f in classified.get("COBOL Code", [])]
        if not cobol_list:
            return jsonify({"error": "No COBOL code found"}), 400
 
        log_processing_step("Generating pseudocode from COBOL code", {
            "cobol_files_count": len(cobol_list),
            "project_id": project_id
        }, 4)
 
        cobol_code_str = "\n".join(cobol_list)
 
 
 
        # 3.5) PERFORM REVERSE ENGINEERING ANALYSIS
        log_processing_step("Performing reverse engineering analysis", {
            "cobol_files_count": len(cobol_list),
            "project_id": project_id
        }, 4.5)
 
        # reverse_engineering_json = reverse_engineer_cobol_code(cobol_code_str, project_id, include_dependencies=True)
 
        # 4) GPT REQUIREMENTS ANALYSIS
        src = data.get("sourceLanguage")
        tgt = data.get("targetLanguage")
 
        if not src:
            return jsonify({"error": "Missing sourceLanguage"}), 400
 
        log_processing_step("Creating business and technical prompts", {
            "source_language": src,
            "target_language": tgt,
            "cobol_files_count": len(cobol_list)
        }, 5)
 
        # Combine COBOL code and analysis
        cobol_code_str = "\n".join(cobol_list)
        cobol_analysis_str = json.dumps(cobol_json, indent=2)
 
        # Add standards context
        standards_context = ""
        if hasattr(current_app, 'standards_documents') and current_app.standards_documents:
            standards_context = f"\n\nSTANDARDS DOCUMENTS CONTEXT:\n{chr(10).join(current_app.standards_documents)}\n"
            logger.info(f"Adding standards context with {len(current_app.standards_documents)} documents")
 
        bus_prompt = create_business_requirements_prompt(src, cobol_code_str) + standards_context + f"\n\nCOBOL ANALYSIS:\n{cobol_analysis_str}"
        tech_prompt = create_technical_requirements_prompt(src, tgt, cobol_code_str) + standards_context + f"\n\nCOBOL ANALYSIS:\n{cobol_analysis_str}"
 
        # Business Requirements Analysis
        business_msgs = [
            {
                "role": "system",
                "content": (
                    f"You are an expert in analyzing COBOL code to extract business requirements. "
                    f"You understand COBOL, CICS commands, and mainframe business processes deeply. "
                    f"You have access to comprehensive analysis results including CICS patterns, standards documents, and COBOL analysis. "
                    f"Use the provided COBOL analysis JSON to understand program structure, variables, and dependencies. "
                    f"Your response must be a valid JSON object following the structure defined below."
                    f"Output your analysis in JSON format with the following structure:\n\n"
                    f"{{\n"
                    f'  "Overview": {{\n'
                    f'    "Purpose of the System": "Describe the system\'s primary function and how it fits into the business.",\n'
                    f'    "Context and Business Impact": "Explain the operational context and value the system provides."\n'
                    f'  }},\n'
                    f'  "Objectives": {{\n'
                    f'    "Primary Objective": "Clearly state the system\'s main goal.",\n'
                    f'    "Key Outcomes": "Outline expected results (e.g., improved processing speed, customer satisfaction)."\n'
                    f'  }},\n'
                    f'  "Business Rules & Requirements": {{\n'
                    f'    "Business Purpose": "Explain the business objective behind this specific module or logic.",\n'
                    f'    "Business Rules": "List the inferred rules/conditions the system enforces.",\n'
                    f'    "Impact on System": "Describe how this part affects the system\'s overall operation.",\n'
                    f'    "Constraints": "Note any business limitations or operational restrictions."\n'
                    f'  }},\n'
                    f'  "Assumptions & Recommendations": {{\n'
                    f'    "Assumptions": "Describe what is presumed about data, processes, or environment.",\n'
                    f'    "Recommendations": "Suggest enhancements or modernization directions."\n'
                    f'  }},\n'
                    f'  "Expected Output": {{\n'
                    f'    "Output": "Describe the main outputs (e.g., reports, logs, updates).",\n'
                    f'    "Business Significance": "Explain why these outputs matter for business processes."\n'
                    f'  }}\n'
                    f"}}"
                    f"CRITICAL - ** THE OUTPUT MUST BE A VALID JSON OBJECT, NO ADDITIONAL TEXT, MARKDOWN, OR EXPLANATIONS OUTSIDE THE JSON **\n"
                )
            },
            {
                "role": "user",
                "content": bus_prompt
            }
        ]
 
        log_processing_step("Running business requirements analysis", {
            "prompt_length": len(bus_prompt)
        }, 6)
 
        business_response = sendtoEGPT(
            business_msgs   )
 
        print(business_response)
 
        log_gpt_interaction("BUSINESS_REQUIREMENTS", AZURE_OPENAI_DEPLOYMENT_NAME, business_msgs, business_response)
 
        business_json = extract_json_from_response(business_response)
 
        # Technical Requirements Analysis
        technical_msgs = [
            {
                "role": "system",
                "content": (
                    f"You are an expert in COBOL to .NET 8 migration. "
                    f"You deeply understand both COBOL and .NET 8 and can identify technical challenges and requirements for migration. "
                    f"Use the provided COBOL analysis JSON to understand program structure, variables, and dependencies. "
                    f"Your response must be a valid JSON object following the structure defined below."
                    f"Output your analysis in JSON format with the following structure:\n"
                    f"{{\n"
                    f'  "technicalRequirements": [\n'
                    f'    {{"id": "TR1", "description": "First technical requirement", "complexity": "High/Medium/Low"}},\n'
                    f'    {{"id": "TR2", "description": "Second technical requirement", "complexity": "High/Medium/Low"}}\n'
                    f'  ],\n'
                    f"}}"
                    f"CRITICAL - ** THE OUTPUT MUST BE A VALID JSON OBJECT, NO ADDITIONAL TEXT, MARKDOWN, OR EXPLANATIONS OUTSIDE THE JSON **\n"
                )
            },
            {
                "role": "user",
                "content": tech_prompt
            }
        ]
 
        log_processing_step("Running technical requirements analysis", {
            "prompt_length": len(tech_prompt)
        }, 7)
 
        technical_response = sendtoEGPT(
            technical_msgs,
 
        )
 
        log_gpt_interaction("TECHNICAL_REQUIREMENTS", AZURE_OPENAI_DEPLOYMENT_NAME, technical_msgs, technical_response)
 
        technical_json = extract_json_from_response(technical_response)
 
        # Save requirements
        output_dir = os.path.join("output", "analysis", project_id)
        os.makedirs(output_dir, exist_ok=True)
        # Save business requirements
        business_req_path = os.path.join(output_dir, "business_requirements.json")
        with open(business_req_path, "w", encoding="utf-8") as f:
            json.dump(business_json, f, indent=2)
        logger.info(f"Business requirements saved to: {business_req_path}")
        # Save technical requirements
        tech_req_path = os.path.join(output_dir, "technical_requirements.json")
        with open(tech_req_path, "w", encoding="utf-8") as f:
            json.dump(technical_json, f, indent=2)
        logger.info(f"Technical requirements saved to: {tech_req_path}")
 
        # Save reverse engineering analysis
        # reverse_engineering_path = os.path.join(output_dir, "reverse_engineering_analysis.json")
        # with open(reverse_engineering_path, "w", encoding="utf-8") as f:
        #     json.dump(reverse_engineering_json, f, indent=2)
        # logger.info(f"Reverse engineering analysis saved to: {reverse_engineering_path}")
 
        # 5) GENERATE TARGET STRUCTURE JSON (USING REQUIREMENTS, AND REVERSE ENGINEERING)
        log_processing_step("Generating target structure analysis with requirements and reverse engineering", {"project_id": project_id}, 8)
        target_structure = create_target_structure_analysis(project_id, file_data, classified, business_json, technical_json)
 
        # 5) INDEX FOR RAG (COMMENTED OUT)
        # log_processing_step("Indexing files for RAG", {"project_id": project_id}, 8)
        # index_files_for_rag(project_id, cobol_json, file_data)
 
        # Store analysis data for conversion use
        current_app.comprehensive_analysis_data = {
            "project_id": project_id,
            "cobol_files": get_cobol_files_for_analysis(classified),
            "classified_files": classified,
            "cobol_analysis": cobol_json,
            # "reverse_engineering": reverse_engineering_json,
            "target_structure": target_structure,
            "analysis_results": {
                "business_requirements": business_json,
                "technical_requirements": technical_json,
                "status": "success"
            }
        }
 
        log_processing_step("Analysis completed successfully", {
            "business_rules_count": len(business_json.get("Business Rules & Requirements", {}).get("Business Rules", [])),
            "technical_requirements_count": len(technical_json.get("technicalRequirements", [])),
            # "reverse_engineering_generated": bool(reverse_engineering_json and "error" not in reverse_engineering_json),
            "target_structure_created": bool(target_structure and "error" not in target_structure),
            "conversionContextReady": True
        }, 9)
 
        return jsonify({
            "status": "success",
            "project_id": project_id,
            "business_requirements": business_json,
            "technical_requirements": technical_json,
            # "reverse_engineering": reverse_engineering_json,
            "target_structure": target_structure,
            "file_classification": classified,
            "cobol_analysis": cobol_json,
            "conversionContextReady": True
        })
 
    except Exception as e:
        logger.error(f"❌ Analysis failed: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
 
@bp.route("/reverse-engineer", methods=["POST"])
def reverse_engineer_cobol():
    """
    Endpoint to perform reverse engineering analysis of COBOL code.
 
    Expected JSON payload:
    {
        "projectId": "unique_project_id",
        "cobolCode": "COBOL source code to analyze",
        "includeDependencies": true/false (optional, default true)
    }
 
    Returns:
    JSON response with comprehensive reverse engineering analysis
    """
    try:
        data = request.json
        log_request_details("REVERSE ENGINEER COBOL", data)
 
        if not data:
            return jsonify({"error": "No data provided"}), 400
 
        project_id = data.get("projectId")
        cobol_code = data.get("cobolCode")
        include_dependencies = data.get("includeDependencies", True)
 
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
 
        if not cobol_code:
            return jsonify({"error": "COBOL code is required"}), 400
 
        log_processing_step("Starting reverse engineering analysis", {
            "project_id": project_id,
            "cobol_code_length": len(cobol_code),
            "include_dependencies": include_dependencies
        }, "REVERSE_ENGINEER_START")
 
        # Perform reverse engineering analysis
        reverse_engineering_result = reverse_engineer_cobol_code(
            cobol_code=cobol_code,
            project_id=project_id,
            include_dependencies=include_dependencies
        )
 
        if "error" in reverse_engineering_result:
            log_processing_step("Reverse engineering failed", {
                "error": reverse_engineering_result["error"],
                "project_id": project_id
            }, "REVERSE_ENGINEER_ERROR")
            return jsonify(reverse_engineering_result), 500
 
        log_processing_step("Reverse engineering completed successfully", {
            "project_id": project_id,
            "analysis_components": list(reverse_engineering_result.keys()) if isinstance(reverse_engineering_result, dict) else []
        }, "REVERSE_ENGINEER_COMPLETE")
 
        return jsonify({
            "status": "success",
            "project_id": project_id,
            "reverse_engineering_analysis": reverse_engineering_result,
            "timestamp": datetime.now().isoformat()
        })
 
    except Exception as e:
        logger.error(f"❌ Reverse engineering failed: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500