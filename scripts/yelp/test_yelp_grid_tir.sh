#!/bin/bash
#SBATCH --gres=gpu:1
#SBATCH --mem=12g
#SBATCH -t 0
#SBATCH --array=1,2,3,4,5,7,8,9,10,11%3
##SBATCH --nodelist=compute-0-7

declare -a pool=("5" "3" "1")
declare -a klw=("0.08" "0.1" "0.15" "0.2")
declare -a anneal=("1" "2")
declare -a nblank=("0.2" "0.3")
declare -a ndrop=("0.1" "0.2" "0.3")

arglen1=${#nblank[@]}
arglen2=${#ndrop[@]}
arglen3=${#anneal[@]}

taskid=${SLURM_ARRAY_TASK_ID}

i=$(( taskid/arglen2/arglen3 ))
j=$(( taskid/arglen2%arglen1 ))
k=$(( taskid%arglen2 ))

python src/main.py \
  --dataset yelp \
  --clean_mem_every 5 \
  --reset_output_dir \
  --classifier_dir="pretrained_classifer/yelp" \
  --data_path data/test/ \
  --train_src_file data/yelp/train.txt \
  --train_trg_file data/yelp/train.attr \
  --dev_src_file data/yelp/dev_li.txt \
  --dev_trg_file data/yelp/dev_li.attr \
  --dev_trg_ref data/yelp/dev_li.txt \
  --src_vocab  data/yelp/text.vocab \
  --trg_vocab  data/yelp/attr.vocab \
  --d_word_vec=128 \
  --d_model=512 \
  --log_every=100 \
  --eval_every=1500 \
  --ppl_thresh=10000 \
  --eval_bleu \
  --batch_size 32 \
  --valid_batch_size 128 \
  --patience 5 \
  --lr_dec 0.5 \
  --lr 0.001 \
  --dropout 0.3 \
  --max_len 10000 \
  --seed 0 \
  --beam_size 1 \
  --word_blank ${nblank[$j]} \
  --word_dropout ${ndrop[$k]} \
  --word_shuffle 3 \
  --cuda \
  --anneal_epoch ${anneal[$i]} \
  --temperature 0.01 \
  --max_pool_k_size 5 \
  --bt \
  --bt_stop_grad \
  # --klw 0.1 \
  # --lm \
  # --avg_len \
  # --gs_soft \
