# Define the Python interpreter
PYTHON = poetry run python

# Define your Python scripts in the directory
SCRIPT1 = example.py
SCRIPT2 = ad_emissions_example_test.py
SCRIPT3 = land_balance_example_test.py
SCRIPT4 = forestry_example_test.py
SCRIPT5 = cattle_ratio_example_test.py
SCRIPT6 = cattle_example_test.py
SCRIPT7 = non_cattle_agriculture_example_test.py
SCRIPT8 = organic_soils_example_test.py

.PHONY: all clean run1 run2 run3

# The 'all' target runs everything in the correct sequence
all: run1 run2 run3 run4 run5 run6 run7 run8
	@echo "=========================================="
	@echo " All Python scripts executed successfully! "
	@echo "=========================================="

# Individual targets for each script
run1: $(SCRIPT1)
	@echo "--> Running Step 1: Full Example..."
	$(PYTHON) $(SCRIPT1)

run2: $(SCRIPT2)
	@echo "--> Running Step 2: AD example..."
	$(PYTHON) $(SCRIPT2)

run3: $(SCRIPT3)
	@echo "--> Running Step 3: Land Balance Example..."
	$(PYTHON) $(SCRIPT3)

run4: $(SCRIPT4)
	@echo "--> Running Step 4: Forestry Example..."
	$(PYTHON) $(SCRIPT4)

run5: $(SCRIPT5)
	@echo "--> Running Step 5: Cattle Ratio Example..."
	$(PYTHON) $(SCRIPT5)	

run6: $(SCRIPT6)
	@echo "--> Running Step 6: Cattle Example..."
	$(PYTHON) $(SCRIPT6)

run7: $(SCRIPT7)
	@echo "--> Running Step 7: Non-Cattle Agriculture Example..."
	$(PYTHON) $(SCRIPT7)

run8: $(SCRIPT8)
	@echo "--> Running Step 8: Organic Soils Example..."
	$(PYTHON) $(SCRIPT8)



# Clean up target (optional: removes cached Python bytecode files)
clean:
	@echo "Cleaning up __pycache__ directories..."
	rm -rf __pycache__
	rm -rf */__pycache__