#!/bin/bash
#SBATCH --partition=class                           # set partition
#SBATCH --account=class                             # Set the account
#SBATCH --qos=high                                  # Set the Quality of Service
#SBATCH --nodes=1                                   # number of nodes to allocate for your job
#SBATCH --ntasks=1                                  # four tasks as we have four GPU's
#SBATCH --ntasks-per-node=1                         # four tasks as we have four GPU's
#SBATCH --cpus-per-task=16                          # every process wants 4 CPUs! - Max allowed is 16 for 24 hr high QOS
#SBATCH --mem=100G                                  # Request 100 GB of memory
#SBATCH -t 4:00:00                                 # set time limit [dd:hh:mm:ss]
#SBATCH --job-name=add_abstract      # set job name
#SBATCH --output=add_abstract.out    # set output name

infile="/fs/class-projects/spring2024/cmsc828j/c828jg00/c828j001/codebase_finder/output/with_code.bib"
outfolder="/fs/class-projects/spring2024/cmsc828j/c828jg00/c828j001/codebase_finder/output/"

# Run the Python script
srun python3 src/scrape_codebases_parallel.py \
    --bib_file $infile \
    --output_dir $outfolder 