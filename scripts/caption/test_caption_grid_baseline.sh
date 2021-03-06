#!/bin/bash
#SBATCH --gres=gpu:1
#SBATCH --mem=12g
#SBATCH -t 0
#SBATCH --array=1-1%1
##SBATCH --nodelist=compute-0-7


export PYTHONPATH="$(pwd)"
export CUDA_VISIBLE_DEVICES="2"

# declare -a pool=("5" "3" "1")
# declare -a klw=("0.08" "0.1" "0.15" "0.2")

declare -a pool=("5")
declare -a klw=("0.1")

for i in "${pool[@]}"
do
  for j in "${klw[@]}"
  do
    CUDA_VISIBLE_DEVICES=$1 python src/main.py \
      --dataset caption \
      --clean_mem_every 5 \
      --reset_output_dir \
      --classifier_dir="pretrained_classifer/caption" \
      --data_path data/test/ \
      --train_src_file data/caption/train.txt \
      --train_trg_file data/caption/train.attr \
      --dev_src_file data/caption/dev.txt \
      --dev_trg_file data/caption/dev.attr \
      --dev_trg_ref data/caption/dev.txt \
      --src_vocab  data/caption/text.vocab \
      --trg_vocab  data/caption/attr.vocab \
      --d_word_vec=128 \
      --d_model=512 \
      --log_every=100 \
      --eval_every=1000 \
      --ppl_thresh=10000 \
      --eval_bleu \
      --batch_size 32 \
      --valid_batch_size 128 \
      --patience 5 \
      --lr_dec 0.8 \
      --lr 0.001 \
      --dropout 0.3 \
      --max_len 10000 \
      --seed 0 \
      --beam_size 1 \
      --word_blank 0.2 \
      --word_dropout 0.1 \
      --word_shuffle 3 \
      --cuda \
      --anneal_epoch 10 \
      --temperature 0.01 \
      --max_pool_k_size $i \
      --bt \
      --bt_stop_grad \
      # --avg_len \
      # --gs_soft \
      # --reload_best \
  done
done
