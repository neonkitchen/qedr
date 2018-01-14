import os
import numpy as np
import datetime, dateutil.tz
import tensorflow as tf
from operator import mul
from functools import reduce

from model import VAE
from lib.models.distributions import Uniform, Categorical, MeanBernoulli, Gaussian
from lib.utils import init_directories, create_directories
from lib.models.data_managers import TeapotsDataManager

#jupyter, AFS only
#os.environ['OUTPUT_DIR'] = "/home/cian/wgan"#"/afs/inf.ed.ac.uk/user/s16/s1668298/msc/wgan"

flags = tf.app.flags
flags.DEFINE_integer("epochs", 25, "Number of epochs to train [25]")
flags.DEFINE_integer("epochs_per_stats", 0.5, "Print/log stats every [epochs_per_stats] epochs. [0.5]")
flags.DEFINE_integer("snapshot_interval", 0.5, "Save checkpoint every [snapshot_interval] epochs. [0.5]")
flags.DEFINE_integer("latent_dim", 10, "Number of latent variables [10]")
flags.DEFINE_float("beta", 1., "D_KL term weighting [1.]")
flags.DEFINE_integer("batch_size", 64, "The size of training batches [64]")
flags.DEFINE_string("image_shape", "(3,64,64)", "Shape of inputs images [(3,64,64)]")
flags.DEFINE_string("exp_name", None, "The name of experiment [None]")
flags.DEFINE_string("arch", "high_cap", "The desired arch: low_cap, high_cap, resnet. [low_cap]")
flags.DEFINE_string("output_dir", "./", "Output directory for checkpoints, samples, etc. [.]")
flags.DEFINE_string("data_dir", None, "Data directory [None]")
flags.DEFINE_string("file_ext", ".jpeg", "Image filename extension [.jpeg]")
flags.DEFINE_boolean("gaps", False, "Create gaps in data to faciliate zero-shot inference [False]")
flags.DEFINE_boolean("train", True, "Train [True]")
flags.DEFINE_boolean("save_codes", False, "Save latent representation or code for all data samples [False]")
flags.DEFINE_boolean("visualize_reconstruct", True, "True for visualizing, False for nothing [False]")
flags.DEFINE_boolean("visualize_disentangle", True, "True for visualizing, False for nothing [False]")
flags.DEFINE_integer("n_disentangle_samples", 10, "The number of evenly spaced samples in latent space \
                     over the interval [-3, 3] [64]")
FLAGS = flags.FLAGS

#exp_name -> no timestamp
#checkpoints -> no timestamp, global step
#function = 'train' -> train=True, save_codes=False (create_dirs...)
                    
# TO DO:
# 1) Separate visualize functions: dis, reconstruct (without trainin)
# 2) Init data manager - file extension (.jpg, .png, .npz)                    

def main(_):
    if FLAGS.exp_name is None:
        FLAGS.exp_name = "vae_{0}_{1}_{2}_{3}".format(FLAGS.gaps, FLAGS.arch, FLAGS.latent_dim, FLAGS.beta)
    image_shape = [int(i) for i in FLAGS.image_shape.strip('()[]{}').split(',')]
    dirs = init_directories(FLAGS.exp_name, FLAGS.output_dir)
    dirs['data'] = '../../data' if FLAGS.data_dir is None else FLAGS.data_dir
    dirs['codes'] = os.path.join(dirs['data'], 'codes/')
    create_directories(dirs, FLAGS.train, FLAGS.save_codes)
    
    z_dist = Gaussian(FLAGS.latent_dim)
    output_dim  = reduce(mul, image_shape, 1)
    output_dist = Gaussian(output_dim)
    
    run_config = tf.ConfigProto(allow_soft_placement=True)
    run_config.gpu_options.allow_growth=True
    run_config.gpu_options.per_process_gpu_memory_fraction=0.9
    sess = tf.Session(config=run_config)

    vae = VAE(
        session=sess,
        output_dist=output_dist,
        z_dist=z_dist,
        arch=FLAGS.arch,
        batch_size=FLAGS.batch_size,
        image_shape=image_shape,
        exp_name=FLAGS.exp_name,
        dirs=dirs,
        beta=FLAGS.beta,
        gaps=FLAGS.gaps,
        vis_reconst=FLAGS.visualize_reconstruct,
        vis_disent=FLAGS.visualize_disentangle,
        n_disentangle_samples=FLAGS.n_disentangle_samples,
    )

    if FLAGS.train:
        data_manager = TeapotsDataManager(dirs['data'], FLAGS.batch_size, shuffle=True, gaps=FLAGS.gaps, 
                                          file_ext=FLAGS.file_ext, train_fract=0.8)
        data_manager.inf_generators()
        vae.train_gen, vae.dev_gen, vae.test_gen = data_manager.get_generators()
        
        n_iters_per_epoch = data_manager.n_train // data_manager.batch_size
        stats_iters = int(FLAGS.epochs_per_stats * n_iters_per_epoch)
        snapshot_interval = int(FLAGS.snapshot_interval * n_iters_per_epoch)
        n_iters = int(FLAGS.epochs * n_iters_per_epoch)
        
        vae.train(n_iters, stats_iters, snapshot_interval)

    if FLAGS.save_codes:
        b_size = 500 #large batch, forward prop only
        data_manager = TeapotsDataManager(dirs['data'], b_size, False, 
                                          False, FLAGS.file_ext, 1.)
        data_manager.set_divisor_batch_size()        
        vae.train_gen, vae.dev_gen, vae.test_gen = data_manager.get_generators()
        
        vae.session.run(tf.global_variables_initializer())
        
        saved_step = vae.load()
        assert saved_step > 1, "A trained model is needed to encode the data!"
        
        codes = []
        for batch_num, (img_batch,) in enumerate(vae.train_gen()):
            code = vae.encode(img_batch) #[batch_size, reg_latent_dim]
            codes.append(code)
            if batch_num < 5 or batch_num % 100 == 0:
                print(("Batch number {0}".format(batch_num)))
        
        codes = np.vstack(codes)         
        filename = os.path.join(dirs['codes'], "codes_" + FLAGS.exp_name)
        np.save(filename, codes)
        print(("Codes saved to: {0}".format(filename)))

if __name__ == '__main__':
    tf.app.run()