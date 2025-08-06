from flask import Blueprint, request, jsonify, current_app
from ..config import logger, AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME, output_dir
from openai import AzureOpenAI
import logging
import os
from ..utils.endpoint import sendtoEGPT
from ..utils.prompts import  create_unit_test_prompt, create_functional_test_prompt
from ..utils.logs import log_request_details, log_processing_step, log_gpt_interaction
from ..utils.response import extract_json_from_response
from ..utils.db_usage import detect_database_usage
from ..utils.db_templates import get_db_template
from ..utils.prompts import  create_cobol_to_dotnet_conversion_prompt
import json
import re
import time
import traceback
import uuid
from pathlib import Path
 
bp = Blueprint('conversion', __name__, url_prefix='/cobo')
 
# client = AzureOpenAI(
#     api_key=AZURE_OPENAI_API_KEY,
#     api_version="2023-05-15",
#     azure_endpoint=AZURE_OPENAI_ENDPOINT,
# )
 
def save_json_response(cobol_filename, json_obj):
    """Save the full JSON response to the json_output directory, using the COBOL filename as base."""
    base_dir = os.path.dirname(output_dir)
    json_output_dir = os.path.join(base_dir, "json_output")
    os.makedirs(json_output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(cobol_filename))[0] if cobol_filename else f"converted_{int(time.time())}"
    output_filename = f"{base_name}_output.json"
    output_path = os.path.join(json_output_dir, output_filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_obj, f, indent=2, ensure_ascii=False)
    return output_path
 
 
 
def extract_project_name(target_structure):
    """Extract project name from target structure"""
    if isinstance(target_structure, dict):
        return target_structure.get("project_name", "BankingSystem")
    return "BankingSystem"
 
def flatten_converted_code(converted_code, unit_test_code=None, project_id=None, target_structure=None):
 
  """Create a standard .NET 8 folder structure and save it to the filesystem."""
 
  files = {}
 
  project_name = extract_project_name(target_structure) if target_structure else "BankingSystem"
 
  test_project_name = f"{project_name}.Tests"
 
  # Process each file in converted_code
 
  if isinstance(converted_code, list):
 
    for file_info in converted_code:
 
      if isinstance(file_info, dict):
 
        file_name = file_info.get("file_name", "")
 
        content = file_info.get("content", "")
 
        path = file_info.get("path", "")
 
        # Clean and construct the file path
 
        if path:
 
          # Remove any trailing file name from path if it matches file_name
 
          if path.endswith(file_name):
 
            path = os.path.dirname(path)
 
          # Ensure path doesn't start with project_name unnecessarily
 
          if path.startswith(project_name + "/") or path.startswith(project_name + "\\"):
 
            file_path = path
 
          else:
 
            file_path = os.path.join(project_name, path, file_name)
 
        else:
 
          file_path = os.path.join(project_name, file_name)
 
        # Normalize path to use correct separators
 
        file_path = os.path.normpath(file_path)
 
        files[file_path] = content
 
  # Add main project file if not exists
 
  if not any(f.endswith(".csproj") for f in files.keys()):
 
    csproj_content = f'''<Project Sdk="Microsoft.NET.Sdk.Web">
 
 <PropertyGroup>
 
 <TargetFramework>net8.0</TargetFramework>
 
 <Nullable>enable</Nullable>
 
 <ImplicitUsings>enable</ImplicitUsings>
 
 </PropertyGroup>
 
 <ItemGroup>
 
 <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
 
 <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" />
 
 <PackageReference Include="Microsoft diapers://x.ai/apiEntityFrameworkCore.Tools" Version="8.0.0" />
 
 <PackageReference Include="Microsoft.EntityFrameworkCore.Design" Version="8.0.0" />
 
 <PackageReference Include="Microsoft.AspNetCore.Authentication.JwtBearer" Version="8.0.0" />
 
 <PackageReference Include="Swashbuckle.AspNetCore" Version="6.4.0" />
 
 <PackageReference Include="Serilog.Extensions.Hosting" Version="8.0.0" />
 
 <PackageReference Include="Serilog.Sinks.Console" Version="5.0.0" />
 
 <PackageReference Include="Serilog.Sinks.File" Version="5.0.0" />
 
 <PackageReference Include="AutoMapper.Extensions.Microsoft.DependencyInjection" Version="12.0.0" />
 
 <PackageReference Include="FluentValidation.AspNetCore" Version="11.0.0" />
 
 </ItemGroup>
 
</Project>'''
 
    files[os.path.join(project_name, f"{project_name}.csproj")] = csproj_content
 
  # Add appsettings.json if not exists
 
  if not any("appsettings.json" in f for f in files.keys()):
 
    appsettings_content = '''{
 
 "ConnectionStrings": {
 
 "DefaultConnection": "Server=localhost;Database=BankingSystem;Trusted_Connection=true;TrustServerCertificate=true;"
 
 },
 
 "Logging": {
 
 "LogLevel": {
 
  "Default": "Information",
 
  "Microsoft.AspNetCore": "Warning",
 
  "Microsoft.EntityFrameworkCore.Database.Command": "Information"
 
 }
 
 },
 
 "AllowedHosts": "*"
 
}'''
 
    files[os.path.join(project_name, "appsettings.json")] = appsettings_content
 
  # Add test project csproj file
 
  test_csproj_content = f'''<Project Sdk="Microsoft.NET.Sdk">
 
 <PropertyGroup>
 
 <TargetFramework>net8.0</TargetFramework>
 
 <IsPackable>false</IsPackable>
 
 <IsTestProject>true</IsTestProject>
 
 </PropertyGroup>
 
 <ItemGroup>
 
 <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
 
 <PackageReference Include="xunit" Version="2.4.2" />
 
 <PackageReference Include="xunit.runner.visualstudio" Version="2.4.5" />
 
 <PackageReference Include="Moq" Version="4.20.70" />
 
 <PackageReference Include="Microsoft.EntityFrameworkCore.InMemory" Version="8.0.0" />
 
 <PackageReference Include="FluentAssertions" Version="6.12.0" />
 
 </ItemGroup>
 
 <ItemGroup>
 
 <ProjectReference Include="../{project_name}/{project_name}.csproj" />
 
 </ItemGroup>
 
</Project>'''
 
  files[os.path.join(test_project_name, f"{test_project_name}.csproj")] = test_csproj_content
 
  # Add unit test files if unit_test_code is provided
 
  if unit_test_code:
 
    logger.info(f"Processing unit test code: {type(unit_test_code)}")
 
    if isinstance(unit_test_code, list):
 
      for test_file in unit_test_code:
 
        if isinstance(test_file, dict):
 
          file_name = test_file.get("fileName")
 
          content = test_file.get("content", "")
 
          if file_name and content:
 
            files[os.path.join(test_project_name, "Tests", file_name)] = content
 
            logger.info(f"Added unit test file: {file_name}")
 
    elif isinstance(unit_test_code, dict):
 
      if "unitTestFiles" in unit_test_code:
 
        for test_file in unit_test_code["unitTestFiles"]:
 
          if isinstance(test_file, dict):
 
            file_name = test_file.get("fileName")
 
            content = test_file.get("content", "")
 
            if file_name and content:
 
              files[os.path.join(test_project_name, file_name)] = content
 
              logger.info(f"Added unit test file: {file_name}")
 
      else:
 
        for file_name, content in unit_test_code.items():
 
          if content:
 
            files[os.path.join(test_project_name, file_name)] = content
 
            logger.info(f"Added unit test file: {file_name}")
 
    elif isinstance(unit_test_code, str):
 
      if unit_test_code.strip():
 
        files[os.path.join(test_project_name, "UnitTests.cs")] = unit_test_code
 
        logger.info("Added single unit test file: UnitTests.cs")
 
  # Add solution file
 
  sln_content = f'''
 
Microsoft Visual Studio Solution File, Format Version 12.00
 
# Visual Studio Version 17
 
VisualStudioVersion = 17.0.31912.275
 
MinimumVisualStudioVersion = 10.0.40219.1
 
Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{project_name}", "{project_name}/{project_name}.csproj", "{{11111111-1111-1111-1111-111111111111}}"
 
EndProject
 
Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{test_project_name}", "{test_project_name}/{test_project_name}.csproj", "{{22222222-2222-2222-2222-222222222222}}"
 
EndProject
 
Global
 
 GlobalSection(SolutionConfigurationPlatforms) = preSolution
 
  Debug|Any CPU = Debug|Any CPU
 
  Release|Any CPU = Release|Any CPU
 
 EndGlobalSection
 
 GlobalSection(ProjectConfigurationPlatforms) = postSolution
 
  {{11111111-1111-1111-1111-111111111111}}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
 
  {{11111111-1111-1111-1111-111111111111}}.Debug|Any CPU.Build.0 = Debug|Any CPU
 
  {{11111111-1111-1111-1111-111111111111}}.Release|Any CPU.ActiveCfg = Release|Any CPU
 
  {{11111111-1111-1111-1111-111111111111}}.Release|Any CPU.Build.0 = Release|Any CPU
 
  {{22222222-2222-2222-2222-222222222222}}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
 
  {{22222222-2222-2222-2222-222222222222}}.Debug|Any CPU.Build.0 = Debug|Any CPU
 
  {{22222222-2222-2222-2222-222222222222}}.Release|Any CPU.ActiveCfg = Release|Any CPU
 
  {{22222222-2222-2222-2222-222222222222}}.Release|Any CPU.Build.0 = Release|Any CPU
 
 EndGlobalSection
 
EndGlobal
 
'''.strip()
 
  files[os.path.join(project_name + ".sln")] = sln_content
 
  # Save files to the filesystem
 
  if project_id:
 
    output_dir_path = os.path.join("output", "converted", project_id)
 
    os.makedirs(output_dir_path, exist_ok=True)
 
    for file_path, content in files.items():
           
       
 
        if not file_path or not content:
            logger.warning(f"Skipping file due to missing path or content: {file_path}")
            continue
 
 
        full_path = os.path.join(output_dir_path, file_path)
 
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
 
        try:
 
            with open(full_path, "w", encoding="utf-8") as f:
 
                f.write(content)
 
            logger.info(f"Saved file: {full_path}")
 
        except Exception as e:
 
            logger.error(f"Error saving file {full_path}: {str(e)}")
 
            raise
 
  # Post-processing: Ensure appsettings.json and Program.cs are correct
 
  appsettings_keys = [k for k in files if k.lower().endswith("appsettings.json") and k != os.path.join(project_name, "appsettings.json")]
 
  for key in appsettings_keys:
 
    files[os.path.join(project_name, "appsettings.json")] = files[key]
 
    del files[key]
 
  program_cs_path = os.path.join(project_name, "Program.cs")
 
  if not any(k.lower() == program_cs_path.lower() for k in files):
 
    files[program_cs_path] = '''
 
using Microsoft.AspNetCore.Builder;
 
using Microsoft.EntityFrameworkCore;
 
using Microsoft.Extensions.DependencyInjection;
 
using Microsoft.Extensions.Hosting;
 
using BankingSystem.Data;
 
using BankingSystem.Repositories;
 
var builder = WebApplication.CreateBuilder(args);
 
// Add services to the container.
 
builder.Services.AddControllers();
 
// Configure Entity Framework Core
 
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection");
 
builder.Services.AddDbContext<ApplicationDbContext>(options =>
 
  options.UseSqlServer(connectionString));
 
// Register repositories
 
builder.Services.AddScoped(typeof(IGenericRepository<>), typeof(GenericRepository<>));
 
var app = builder.Build();
 
// Configure the HTTP request pipeline.
 
if (app.Environment.IsDevelopment())
 
{
 
  app.UseDeveloperExceptionPage();
 
}
 
app.UseHttpsRedirection();
 
app.UseAuthorization();
 
app.MapControllers();
 
// Ensure database is created
 
using (var scope = app.Services.CreateScope())
 
{
 
  var dbContext = scope.ServiceProvider.GetRequiredService<ApplicationDbContext>();
 
  dbContext.Database.EnsureCreated();
 
}
 
app.Run();
 
'''
 
  return files
 
 
def get_source_code_from_project(project_id):
    """Get source code from uploaded project files"""
    try:
        # Load from comprehensive analysis data if available
        if hasattr(current_app, 'comprehensive_analysis_data') and current_app.comprehensive_analysis_data:
            project_data = current_app.comprehensive_analysis_data
            if project_data.get('project_id') == project_id:
                cobol_files = project_data.get('cobol_files', {})
                if cobol_files:
                    logger.info(f"Found {len(cobol_files)} COBOL files in analysis data")
                    return cobol_files
 
        # Fallback: Load from uploads directory
        uploads_dir = Path("uploads") / project_id
        if uploads_dir.exists():
            source_code = {}
            for file_path in uploads_dir.glob("**/*"):
                if file_path.is_file() and file_path.suffix.lower() in ['.cbl', '.cpy', '.jcl']:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        source_code[file_path.name] = f.read()
 
            if source_code:
                logger.info(f"Loaded {len(source_code)} files from uploads directory")
                return source_code
 
        logger.warning(f"No source code found for project {project_id}")
        return {}
 
    except Exception as e:
        logger.error(f"Error getting source code for project {project_id}: {str(e)}")
        return {}
 
def load_analysis_data(project_id):
    """Load analysis data including cobol_analysis.json, target_structure.json"""
    analysis_data = {}
 
    # Load COBOL analysis
    cobol_analysis_path = os.path.join("output", "analysis", project_id, "cobol_analysis.json")
    if os.path.exists(cobol_analysis_path):
        with open(cobol_analysis_path, "r", encoding="utf-8") as f:
            analysis_data["cobol_analysis"] = json.load(f)
        logger.info(f"Loaded COBOL analysis for project: {project_id}")
    else:
        logger.warning(f"COBOL analysis not found for project: {project_id}")
 
    # Load target structure
    target_structure_path = os.path.join("output", "analysis", project_id, "target_structure.json")
    if os.path.exists(target_structure_path):
        with open(target_structure_path, "r", encoding="utf-8") as f:
            analysis_data["target_structure"] = json.load(f)
        logger.info(f"Loaded target structure for project: {project_id}")
    else:
        logger.warning(f"Target structure not found for project: {project_id}")
 
 
    # Load reverse engineering analysis
    reverse_engineering_path = os.path.join("output", "analysis", project_id, "reverse_engineering_analysis.json")
    if os.path.exists(reverse_engineering_path):
        with open(reverse_engineering_path, "r", encoding="utf-8") as f:
            analysis_data["reverse_engineering"] = json.load(f)
        logger.info(f"Loaded reverse engineering analysis for project: {project_id}")
    else:
        logger.warning(f"Reverse engineering analysis not found for project: {project_id}")
 
    business_requirements_path = os.path.join("output", "analysis", project_id, "business_requirements.json")
    if os.path.exists(business_requirements_path):
        with open(business_requirements_path, "r", encoding="utf-8") as f:
            analysis_data["business_requirements"] = json.load(f)
        logger.info(f"Loaded business requirements for project: {project_id}")
    else:
        logger.warning(f"Business Requirements not found for project: {project_id}")
 
    technical_requirements_path = os.path.join("output", "analysis", project_id, "technical_requirements.json")
    if os.path.exists(technical_requirements_path):
        with open(technical_requirements_path, "r", encoding="utf-8") as f:
            analysis_data["technical_requirements"] = json.load(f)
        logger.info(f"Loaded technical requirements for project: {project_id}")
    else:
        logger.warning(f"Technical Requirements not found for project: {project_id}")
 
    return analysis_data
 
@bp.route("/convert", methods=["POST"])
def convert_cobol_to_csharp():
    try:
        data = request.json
        project_id = data.get("projectId")
 
        if not project_id:
            logger.error("Project ID is missing in request")
            return jsonify({"error": "Project ID is missing. Please upload files first.", "files": {}}), 400
 
        logger.info(f"Starting conversion for project: {project_id}")
 
        # Load analysis data (cobol_analysis.json and target_structure.json)
        analysis_data = load_analysis_data(project_id)
 
        if not analysis_data.get("cobol_analysis"):
            logger.error(f"No COBOL analysis data found for project: {project_id}")
            return jsonify({"error": "No analysis data found. Please run analysis first.", "files": {}}), 400
 
        cobol_json = analysis_data["cobol_analysis"]
        target_structure = analysis_data.get("target_structure", {})
        business_requirements = analysis_data.get("business_requirements", {})
        technical_requirements = analysis_data.get("technical_requirements", {})
        reverse_engineering = analysis_data.get("reverse_engineering", {})
 
        logger.info(f"Loaded analysis data for project: {project_id}")
        logger.info(f"Reverse engineering available: {bool(reverse_engineering)}")
 
        # Get source code - try multiple sources
        source_code = {}
 
        # First try: from request data
        request_source_code = data.get("sourceCode", {})
        if request_source_code:
            logger.info("Using source code from request")
            if isinstance(request_source_code, str):
                try:
                    request_source_code = json.loads(request_source_code)
                except json.JSONDecodeError:
                    logger.error("Failed to parse sourceCode from request")
                    request_source_code = {}
 
            # Extract content from file objects
            for file_name, file_data in request_source_code.items():
                if isinstance(file_data, dict) and 'content' in file_data:
                    source_code[file_name] = file_data['content']
                elif isinstance(file_data, str):
                    source_code[file_name] = file_data
 
        # Second try: from project files
        if not source_code:
            logger.info("Getting source code from project files")
            source_code = get_source_code_from_project(project_id)
 
        # Validate source code
        if not source_code:
            logger.error(f"No source code found for project: {project_id}")
            return jsonify({"error": "No source code found. Please upload COBOL files first.", "files": {}}), 400
 
        # Filter only COBOL-related files
        cobol_code_list = []
        for file_name, content in source_code.items():
            if isinstance(content, str) and content.strip():
                # Check if it's a COBOL file
                if (file_name.lower().endswith(('.cbl', '.cpy', '.jcl')) or
                    any(keyword in content.upper() for keyword in ['IDENTIFICATION DIVISION', 'PROGRAM-ID', 'PROCEDURE DIVISION', 'WORKING-STORAGE'])):
                    cobol_code_list.append(content)
                    logger.info(f"Added COBOL file: {file_name}")
 
        if not cobol_code_list:
            logger.error("No valid COBOL code found in source files")
            return jsonify({"error": "No valid COBOL code found for conversion.", "files": {}}), 400
 
        logger.info(f"Found {len(cobol_code_list)} COBOL files for conversion")
 
        # Prepare conversion data
        print(cobol_code_list)
        cobol_code_str = "\n".join(cobol_code_list)
        print(cobol_code_str)
        target_structure_str = json.dumps(target_structure, indent=2)
        business_requirements_str = json.dumps(business_requirements, indent=2)
        technical_requirements_str = json.dumps(technical_requirements, indent=2)
        reverse_engineering_str = json.dumps(reverse_engineering, indent=2) if reverse_engineering else "{}"
 
        # Load RAG context
        # vector_store = load_vector_store(project_id)
        # rag_context = ""
        # standards_context = ""
        # if vector_store:
        #     rag_results = query_vector_store(vector_store, "Relevant COBOL program and C# conversion patterns", k=5)
        #     if rag_results:
        #         rag_context = "\n\nRAG CONTEXT:\n" + "\n".join([f"Source: {r.metadata.get('source', 'unknown')}\n{r.page_content}\n" for r in rag_results])
        #         standards_results = query_vector_store(vector_store, "Relevant coding standards and guidelines", k=3)
        #         if standards_results:
        #             standards_context = "\n\nSTANDARDS CONTEXT:\n" + "\n".join([f"Source: {r.metadata.get('source', 'unknown')}\n{r.page_content}\n" for r in standards_results])
        #         logger.info("Added RAG and standards context")
        #     else:
        #         logger.warning("No RAG results returned from vector store")
 
        # Detect database usage and get DB template
        db_usage = detect_database_usage(cobol_code_str, source_language="COBOL")
        db_type = db_usage.get("db_type", "none")
 
        # Use enhanced EF Core template for better implementation
        if db_usage.get("has_db", False):
            db_setup_template = get_db_template("C# Advanced")
            logger.info("Using advanced Entity Framework Core template")
        else:
            db_setup_template = get_db_template("C#")
            logger.info("Using standard Entity Framework Core template")
 
        # Create conversion prompt using the imported function
        base_conversion_prompt = create_cobol_to_dotnet_conversion_prompt()
 
        # Enhanced conversion prompt with additional context
        conversion_prompt = f"""
 
        **CONVERSION TASK: Convert COBOL to C# .NET 8**
 
        Very Important - Please generate data retrieval logic extract, extract business losgic and implement in .net 8 properly, do reasoning and then geenrate good output
 
        **Conversion Prompts**
        {base_conversion_prompt}
 
        **SOURCE CODE:**
        {cobol_code_str}
 
        **Target Structure**
        {target_structure_str}
 
        **DATABASE SETUP TEMPLATE:**
        {db_setup_template}
 
        **BUSINESS REQUIREMENTS (IMPLEMENT ALL OF THESE):**
        {business_requirements_str}
 
        **TECHNICAL REQUIREMENTS:**
        {technical_requirements_str}
 
        **MANDATORY: Each service method must:**
        1. Have complete parameter validation with detailed error messages
        2. Include comprehensive error handling with try-catch blocks and specific exception types
        3. Log entry and exit points with detailed context information
        4. Return appropriate response objects with proper status codes and messages
        5. Handle null checks and edge cases with defensive programming
        6. Include business rule validation based on COBOL logic
        7. Implement actual business logic from COBOL source code analysis
        8. Use proper async/await patterns for database operations
        9. Include data transformation and mapping logic
        10. Implement caching strategies where appropriate
        11. Add performance monitoring and metrics
        12. Include comprehensive input sanitization and validation
 
 
        **Important Instructions**
        - Ensure all business logic is preserved and converted accurately.
        - Use modern .NET 8 patterns and practices.
        - Implement proper error handling and validation.
        - Follow SOLID principles and clean architecture.
        - Use dependency injection for services and repositories.
        - Implement logging using Serilog.
        - Use Entity Framework Core for database interactions.
        - Ensure all converted code is well-structured and maintainable.
        - **SERVICE IMPLEMENTATION REQUIREMENTS:**
          * Analyze COBOL data structures and convert to proper C# models
          * Extract business rules from COBOL PROCEDURE DIVISION and implement as service methods
          * Convert COBOL file operations to database operations using Entity Framework
          * Implement data validation based on COBOL WORKING-STORAGE definitions
          * Convert COBOL arithmetic operations to C# equivalents with proper error handling
          * Map COBOL record structures to C# DTOs and entities
          * Implement transaction management for multi-step operations
          * Add comprehensive logging for audit trails
          * Include performance optimization for large data sets
          * Implement proper exception handling for business rule violations
 
        **CRITICAL: NO PLACEHOLDER COMMENTS ALLOWED**
        - Do NOT use placeholder comments or TODO statements
        - Do NOT use comments like "// TODO: Implement this method"
        - EVERY method must have a complete, working implementation with actual business logic
        - If you cannot determine the exact business logic, implement a reasonable default with proper error handling
        - Use the COBOL source code analysis to understand the actual business rules and data flow
        - **SERVICE METHOD REQUIREMENTS:**
          * Each service method must contain actual implementation logic
          * Convert COBOL PERFORM statements to appropriate C# method calls
          * Implement COBOL IF-THEN-ELSE logic as proper C# conditional statements
          * Convert COBOL arithmetic operations (ADD, SUBTRACT, MULTIPLY, DIVIDE) to C# equivalents
          * Map COBOL data validation rules to C# validation logic
          * Implement COBOL file read/write operations as database queries
          * Convert COBOL sort operations to LINQ OrderBy/ThenBy
          * Implement COBOL search logic using LINQ Where clauses
          * Add proper null checking and defensive programming
          * Include comprehensive error handling for all operations
 
 
 
        **REQUIRED OUTPUT:** Provide a complete C# .NET 8 solution with proper folder structure
        """
 
        # Call Azure OpenAI for conversion
        conversion_msgs = [
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer with deep expertise in COBOL-to-.NET 8 migrations. "
                    "Your task is to analyze and convert COBOL source code into a fully functional, production-ready .NET 8 C# application.\n\n"
 
                    "**CORE RESPONSIBILITIES:**\n"
                    "- Perform comprehensive reverse engineering of COBOL code to extract business logic, data processing rules, and algorithms.\n"
                    "- Convert COBOL logic into clean, maintainable, and scalable C# code using modern .NET 8 features.\n"
                    "- Apply enterprise-grade architecture patterns, including Clean Architecture, SOLID principles, and dependency injection.\n"
                    "- Accurately preserve and implement all original business logic in the migrated application.\n"
                    "- Ensure code is robust, performant, and production-ready, including proper error handling and logging.\n\n"
 
                    "**SERVICE IMPLEMENTATION GUIDELINES:**\n"
                    "- **Data Access Layer:** Convert COBOL file operations to Entity Framework Core database operations\n"
                    "- **Business Logic:** Extract and implement all business rules from COBOL PROCEDURE DIVISION\n"
                    "- **Validation:** Convert COBOL data validation rules to C# validation attributes and custom validators\n"
                    "- **Error Handling:** Implement comprehensive exception handling with specific exception types\n"
                    "- **Logging:** Add detailed logging for all operations with structured logging patterns\n"
                    "- **Performance:** Implement caching, pagination, and optimization for large datasets\n"
                    "- **Security:** Add input sanitization, SQL injection prevention, and proper authentication\n"
                    "- **Testing:** Include comprehensive unit tests and integration tests\n\n"
 
                    "**COBOL TO C# MAPPING PATTERNS:**\n"
                    "- COBOL PERFORM → C# method calls with proper async/await\n"
                    "- COBOL IF-THEN-ELSE → C# if/else statements with null checking\n"
                    "- COBOL arithmetic (ADD/SUBTRACT/MULTIPLY/DIVIDE) → C# arithmetic with overflow checking\n"
                    "- COBOL file operations → Entity Framework Core queries with proper LINQ\n"
                    "- COBOL sort operations → LINQ OrderBy/ThenBy with proper comparers\n"
                    "- COBOL search logic → LINQ Where clauses with optimized queries\n"
                    "- COBOL data validation → C# validation attributes and custom validators\n"
                    "- COBOL transaction management → Entity Framework Core transactions\n\n"
 
                    "**CRITICAL REQUIREMENTS:**\n"
                    "- DO NOT generate placeholder comments or TODOs.\n"
                    "- DO NOT skip or partially implement any logic.\n"
                    "- DO NOT ignore complex COBOL constructs — you must provide complete modern equivalents.\n"
                    "- DO NOT hardcode values intended for configuration files.\n"
                    "- EVERY service method must contain actual implementation logic.\n"
                    "- Implement proper async/await patterns for all database operations.\n"
                    "- Include comprehensive error handling and validation.\n\n"
 
                    "**DELIVERABLE FORMAT:**\n"
                    "Return the output as a JSON object in the following format:\n"
                    "{\n"
                    "  \"converted_code\": [\n"
                    "    {\n"
                    "      \"file_name\": \"string\",\n"
                    "      \"path\": \"string\",\n"
                    "      \"content\": \"string\"\n"
                    "    }\n"
                    "  ],\n"
                    "  \"conversion_notes\": [\n"
                    "    {\"note\": \"string\", \"severity\": \"Info\" | \"Warning\" | \"Error\"}\n"
                    "  ]\n"
                    "}\n\n"
 
                    "**QUALITY STANDARDS:**\n"
                    "- The code must compile without errors.\n"
                    "- All business logic must be faithfully preserved and implemented.\n"
                    "- Use idiomatic C# naming conventions and modern .NET 8 features.\n"
                    "- Implement input validation, exception safety, and logging.\n"
                    "- Ensure thread safety and performance optimization where appropriate.\n"
                    "- Include comprehensive unit tests for all business logic.\n"
                )
            },
 
            {
                "role": "user",
                "content": conversion_prompt
            }
        ]
 
        logger.info("Calling Azure OpenAI for conversion")
 
        if reverse_engineering:
            logger.info(f"Using reverse engineering analysis for comprehensive conversion insights")
        else:
            logger.warning("No reverse engineering analysis available - conversion will proceed without deep structural insights")
 
        conversion_response = sendtoEGPT(
           conversion_msgs,
        )
 
        print(conversion_response)
 
        # logger.info(f"Conversion response received. Usage: {conversion_response.usage}")
 
        # Extract and parse the JSON response
        converted_json = extract_json_from_response(conversion_response)
 
        if not converted_json:
            logger.error("Failed to extract JSON from conversion response")
            return jsonify({"error": "Failed to process conversion response.", "files": {}}), 500
 
        # --- BEGIN: Unit and Functional Test Generation Integration ---
        # Extract Controllers and Services for test generation
        converted_code = converted_json.get("converted_code", [])
        # Try to extract Controllers and Services from the converted_code list
        controllers = []
        print(controllers)
        services = []
        print(services)
        for file_info in converted_code:
            if isinstance(file_info, dict):
                file_name = file_info.get("file_name", "")
                path = file_info.get("path", "")
                content = file_info.get("content", "")
                # Heuristics: look for 'Controller' or 'Service' in file name or path
                if "controller" in file_name.lower() or "controller" in path.lower():
                    controllers.append({"file_name": file_name, "path": path, "content": content})
                if "service" in file_name.lower() or "service" in path.lower():
                    services.append({"file_name": file_name, "path": path, "content": content})
 
        # Compose a minimal dict to pass to the unit/functional test prompt
        unit_test_input = {
            "Controllers": controllers,
            "Services": services
        }
        print("[DEBUG] Extracted controllers:", controllers)
        print("[DEBUG] Extracted services:", services)
 
        # Generate unit test prompt
        print("[DEBUG] Creating unit test prompt with input:", unit_test_input)
        unit_test_prompt = create_unit_test_prompt(
            "C#",
            unit_test_input,
        )
        unit_test_system = (
            "You are an expert test engineer specializing in writing comprehensive unit tests for .NET 8 applications. "
            "For EACH Controller class found, generate a separate unit test file named '[ControllerName]Tests.cs'. "
            "Return your response in JSON as follows:\n"
            "{\n"
            '  "unitTestFiles": [{'
            '       "fileName": "[ControllerName]Tests.cs",'
            '       "content": "...unit test code..."'
            '   }, ...],'
            '  "testDescription": "...",'
            '  "coverage": [...],'
            '  "businessRuleTests": [...]'
            "}\n"
        )
 
        unit_test_messages = [
            {"role": "system", "content": unit_test_system},
            {"role": "user", "content": unit_test_prompt}
        ]
        print("[DEBUG] Sending unit test messages to LLM:", unit_test_messages)
        try:
            unit_test_response = sendtoEGPT(
                unit_test_messages,
 
            )
            unit_test_content = unit_test_response.strip()
            print("[DEBUG] Raw unit test LLM response:", unit_test_content)
            try:
                unit_test_json = json.loads(unit_test_content)
                print("[DEBUG] Parsed unit test JSON:", unit_test_json)
                logger.info("✅ Unit test JSON parsed successfully")
            except json.JSONDecodeError:
                logger.warning("⚠️ Failed to parse unit test JSON directly")
                unit_test_json = extract_json_from_response(unit_test_content)
                print("[DEBUG] Extracted unit test JSON via fallback:", unit_test_json)
            # Fix: Extract unit test files correctly from the JSON
            unit_test_code = unit_test_json.get("unitTestFiles")
            if not unit_test_code:
                unit_test_code = unit_test_json.get("unitTestCode", "")
            print("[DEBUG] Final unit test code:", unit_test_code)
        except Exception as e:
            logger.error(f"Unit test generation failed: {e}")
            print("[ERROR] Exception during unit test generation:", e)
            try:
                unit_test_json = json.loads(unit_test_content)
                print("[DEBUG] Exception fallback, parsed unit test JSON:", unit_test_json)
                unit_test_code = unit_test_json.get("unitTestFiles", [])
            except Exception as ex:
                print("[ERROR] Exception fallback also failed:", ex)
                unit_test_json = {}
                unit_test_code = []
 
        # Generate functional test prompt
        functional_test_prompt = create_functional_test_prompt(
            "C#",
            unit_test_input
        )
        functional_test_system = (
            "You are an expert QA engineer specializing in creating functional tests for .NET 8 applications. "
            "You create comprehensive test scenarios that verify the application meets all business requirements. "
            "Focus on user journey tests, acceptance criteria, and business domain validation. "
            "Return your response in JSON format with the following structure:\n"
            "{\n"
            '  "functionalTests": [\n'
            '    {"id": "FT1", "title": "Test scenario title", "steps": ["Step 1", "Step 2"], "expectedResult": "Expected outcome", "businessRule": "Related business rule"},\n'
            '    {"id": "FT2", "title": "Another test scenario", "steps": ["Step 1", "Step 2"], "expectedResult": "Expected outcome", "businessRule": "Related business rule"}\n'
            '  ],\n'
            '  "testStrategy": "Description of the overall testing approach",\n'
            '  "domainCoverage": ["List of business domain areas covered"]\n'
            "}"
        )
        functional_test_messages = [
            {"role": "system", "content": functional_test_system},
            {"role": "user", "content": functional_test_prompt}
        ]
        try:
            functional_test_response = sendtoEGPT(
                functional_test_messages,
 
            )
            functional_test_content = functional_test_response.strip()
            try:
                functional_test_json = json.loads(functional_test_content)
                logger.info("✅ Functional test JSON parsed successfully")
            except json.JSONDecodeError:
                logger.warning("⚠️ Failed to parse functional test JSON directly")
                functional_test_json = extract_json_from_response(functional_test_content)
        except Exception as e:
            logger.error(f"Functional test generation failed: {e}")
            functional_test_json = {}
        # --- END: Unit and Functional Test Generation Integration ---
 
        # Save converted code JSON
        output_dir_path = os.path.join("output", "converted", project_id)
        os.makedirs(output_dir_path, exist_ok=True)
        output_path = os.path.join(output_dir_path, "converted_csharp.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(converted_json, f, indent=2)
        logger.info(f"Converted C# code saved to: {output_path}")
 
        # Create and save .NET folder structure
        files = flatten_converted_code(
            converted_json.get("converted_code", []),
            unit_test_code,
            project_id,
            target_structure
        )
 
        logger.info(f"Generated {len(files)} files for .NET project")
 
        return jsonify({
            "status": "success",
            "project_id": project_id,
            "converted_code": converted_json.get("converted_code", []),
            "conversion_notes": converted_json.get("conversion_notes", []),
            "unit_tests": unit_test_code,
            "unit_test_details": unit_test_json,
            "functional_tests": functional_test_json,
            "files": files,
 
            "reverse_engineering_used": bool(reverse_engineering),
            "conversion_quality": "enhanced" if (reverse_engineering) else "standard"
        })
 
    except Exception as e:
        logger.error(f"❌ Conversion failed: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e), "files": {}}), 500
 
 
@bp.route("/converted-files/<base_name>", methods=["GET"])
def get_converted_files(base_name):
    """Return the file tree and contents for a given conversion (by base_name) from ConvertedCode."""
    try:
        converted_code_dir = os.path.join("output", "converted", base_name)
        if not os.path.exists(converted_code_dir):
            return jsonify({"error": "Converted files not found"}), 404
 
        file_tree = {"files": {}}
        for root, dirs, files in os.walk(converted_code_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, converted_code_dir)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_tree["files"][rel_path] = f.read()
                except Exception as e:
                    logger.error(f"Error reading file {file_path}: {str(e)}")
                    file_tree["files"][rel_path] = f"Error reading file: {str(e)}"
 
        return jsonify(file_tree)
    except Exception as e:
        logger.error(f"Error getting converted files: {str(e)}")
        return jsonify({"error": str(e)}), 500