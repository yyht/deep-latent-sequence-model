#!/bin/bash
#SBATCH --gres=gpu:1
#SBATCH --mem=12g
##SBATCH --nodelist=compute-0-7
#SBATCH -t 0

export PYTHONPATH="$(pwd)"
export CUDA_VISIBLE_DEVICES="2"

declare -a anneal=("-1" "1" "5" "10" "30" "50")

for i in "${anneal[@]}"
do
  CUDA_VISIBLE_DEVICES=$1 python src/main.py \
    --dataset shakespeare \
    --clean_mem_every 5 \
    --reset_output_dir \
    --classifier_dir="pretrained_classifer/shakespeare" \
    --data_path data/test/ \
    --train_src_file data/shakespeare/train.txt \
    --train_trg_file data/shakespeare/train.attr \
    --dev_src_file data/shakespeare/dev.txt \
    --dev_trg_file data/shakespeare/dev.attr \
    --dev_trg_ref data/shakespeare/dev_ref.txt \
    --src_vocab  data/shakespeare/text.vocab \
    --trg_vocab  data/shakespeare/attr.vocab \
    --d_word_vec=128 \
    --d_model=512 \
    --log_every=100 \
    --eval_every=1000 \
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
    --word_blank 0.2 \
    --word_dropout 0.1 \
    --word_shuffle 3 \
    --cuda \
    --anneal_epoch $i \
    --temperature 0.01 \
    --max_pool_k_size 5 \
    --bt \
    --bt_stop_grad \
    # --gumbel_softmax \
    # --lm \
    # --avg_len \
    # --gs_soft \
done
